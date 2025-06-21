# rag/training.py
# Parses Apache logs, loads into PostgreSQL DB, labels entries with scores,
# extracts features, trains RandomForest, AND saves data for LLM fine-tuning.
# This version is refactored for high performance using pandas.

import pandas as pd
import re
import datetime
from collections import defaultdict
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import classification_report, accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
import joblib
import time
import os
from urllib.parse import urlparse
import json
import random
import psycopg2
from psycopg2.extras import DictCursor
from typing import Optional, Dict, Any, List, Tuple

# Attempt to import user-agents library
try:
    from user_agents import parse as ua_parse
    UA_PARSER_AVAILABLE = True
    print("Imported 'user-agents'.")
except ImportError:
    UA_PARSER_AVAILABLE = False
    ua_parse = None
    print("Warning: 'user-agents' not installed.")

# --- Configuration ---
LOG_FILE_PATH = os.getenv("TRAINING_LOG_FILE_PATH", "/app/data/apache_access.log")
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DBNAME = os.getenv("TRAINING_PG_DBNAME", "loganalysisdb")
PG_USER = os.getenv("TRAINING_PG_USER", "loganalysisuser")
PG_PASSWORD_FILE = os.getenv("TRAINING_PG_PASSWORD_FILE", "./secrets/training_pg_password.txt")
MODEL_SAVE_PATH = os.getenv("TRAINING_MODEL_SAVE_PATH", "/app/models/bot_detection_rf_model.joblib")
FINETUNE_DATA_DIR = os.getenv("TRAINING_FINETUNE_DATA_DIR", "/app/data/finetuning_data")
FINETUNE_TRAIN_FILE = os.path.join(FINETUNE_DATA_DIR, "finetuning_data_train.jsonl")
FINETUNE_EVAL_FILE = os.path.join(FINETUNE_DATA_DIR, "finetuning_data_eval.jsonl")
FINETUNE_SPLIT_RATIO = float(os.getenv("TRAINING_FINETUNE_SPLIT_RATIO", 0.15))
MIN_SAMPLES_FOR_TRAINING = int(os.getenv("TRAINING_MIN_SAMPLES", 100))
ROBOTS_TXT_PATH = os.getenv("TRAINING_ROBOTS_TXT_PATH", "/app/config/robots.txt")
HONEYPOT_HIT_LOG = os.getenv("TRAINING_HONEYPOT_LOG", "/app/logs/honeypot_hits.log")
CAPTCHA_SUCCESS_LOG = os.getenv("TRAINING_CAPTCHA_LOG", "/app/logs/captcha_success.log")

KNOWN_BAD_UAS_STR = os.getenv("KNOWN_BAD_UAS", 'python-requests,curl,wget,scrapy,java/,ahrefsbot,semrushbot,mj12bot,dotbot,petalbot,bytespider,gptbot,ccbot,claude-web,google-extended,dataprovider,purebot,scan,masscan,zgrab,nmap')
KNOWN_BAD_UAS = [ua.strip().lower() for ua in KNOWN_BAD_UAS_STR.split(',') if ua.strip()]

KNOWN_BENIGN_CRAWLERS_UAS_STR = os.getenv("KNOWN_BENIGN_CRAWLERS_UAS", 'googlebot,bingbot,slurp,duckduckbot,baiduspider,yandexbot,googlebot-image')
KNOWN_BENIGN_CRAWLERS_UAS = [ua.strip().lower() for ua in KNOWN_BENIGN_CRAWLERS_UAS_STR.split(',') if ua.strip()]


# --- Database Setup ---
def _get_pg_password(password_file_path: str) -> Optional[str]:
    """Loads password from a secret file."""
    # (This function remains unchanged from your original)
    paths_to_try = [
        password_file_path,
        os.path.join("/run/secrets", os.path.basename(password_file_path)),
        os.path.join(os.path.dirname(__file__), '..', 'secrets', os.path.basename(password_file_path))
    ]
    for path in paths_to_try:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return f.read().strip()
            except Exception as e:
                print(f"Warning: Failed to read PostgreSQL password from {path}: {e}")
                continue
    print(f"Error: PostgreSQL password file not found at specified path or fallbacks: {password_file_path}")
    return None

def setup_database() -> Optional[psycopg2.extensions.connection]:
    """Sets up PostgreSQL database and table."""
    # (This function remains unchanged from your original)
    print(f"Setting up PostgreSQL database: {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}")
    if MODEL_SAVE_PATH: os.makedirs(os.path.dirname(MODEL_SAVE_PATH), exist_ok=True)
    if FINETUNE_DATA_DIR: os.makedirs(FINETUNE_DATA_DIR, exist_ok=True)

    conn = None
    pg_password = _get_pg_password(PG_PASSWORD_FILE)
    if not pg_password:
        return None

    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DBNAME,
            user=PG_USER, password=pg_password, connect_timeout=10
        )
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    id SERIAL PRIMARY KEY, ip TEXT NOT NULL, ident TEXT, user_text TEXT,
                    timestamp_iso TIMESTAMPTZ NOT NULL, method TEXT, path TEXT, protocol TEXT,
                    status INTEGER, bytes INTEGER, referer TEXT, user_agent TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_requests_ip_timestamp ON requests (ip, timestamp_iso);
            ''')
        conn.commit()
        print("PostgreSQL database table 'requests' verified.")
        return conn
    except Exception as e:
        print(f"ERROR: PostgreSQL database setup failed: {e}")
        if conn: conn.close()
        return None


# --- Data Loading and Feature Engineering (Refactored for Performance) ---

def load_and_process_logs(conn: psycopg2.extensions.connection) -> pd.DataFrame:
    """
    Loads all logs from the database into a pandas DataFrame and engineers
    all features in a single, efficient pass.
    """
    print("Loading logs from database into pandas DataFrame...")
    query = "SELECT * FROM requests ORDER BY timestamp_iso;"
    df = pd.read_sql(query, conn, index_col='id')
    print(f"Loaded {len(df)} log entries.")

    if df.empty:
        return df

    print("Engineering features...")
    
    # Convert timestamp to datetime objects for calculations
    df['timestamp'] = pd.to_datetime(df['timestamp_iso'])
    
    # Feature: Time-based features
    df['hour_of_day'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.weekday

    # Feature: Request frequency and time since last request (Efficient)
    # This replaces the slow, per-row SQL queries
    df_sorted = df.sort_values(by=['ip', 'timestamp'])
    df['time_since_last_sec'] = df_sorted.groupby('ip')['timestamp'].diff().dt.total_seconds().fillna(-1)
    df['req_freq_60s'] = df_sorted.rolling('60s', on='timestamp', closed='left').count()['ip']
    
    # Feature: User Agent based features
    df['user_agent'] = df['user_agent'].fillna('')
    ua_lower = df['user_agent'].str.lower()
    df['ua_length'] = df['user_agent'].str.len()
    df['ua_is_empty'] = (df['ua_length'] == 0).astype(int)
    df['ua_is_known_bad'] = ua_lower.apply(lambda x: 1 if any(bad in x for bad in KNOWN_BAD_UAS) else 0)
    df['ua_is_known_benign_crawler'] = ua_lower.apply(lambda x: 1 if any(good in x for good in KNOWN_BENIGN_CRAWLERS_UAS) else 0)

    # Feature: Path based features
    df['path'] = df['path'].fillna('')
    df['path_depth'] = df['path'].str.count('/')
    df['path_length'] = df['path'].str.len()
    df['path_is_root'] = (df['path'] == '/').astype(int)
    df['path_is_wp'] = df['path'].str.contains(r'/wp-|/xmlrpc\.php', regex=True).astype(int)
    df['path_disallowed'] = df['path'].apply(is_path_disallowed).astype(int)

    # Feature: Referer based features
    df['referer'] = df['referer'].fillna('')
    df['referer_is_empty'] = (df['referer'] == '').astype(int)
    
    print("Feature engineering complete.")
    return df

# --- Robots.txt and Feedback Loading ---
disallowed_paths: set[str] = set()

def load_robots_txt(path: str):
    """Loads and parses robots.txt for disallowed paths."""
    # (This function remains unchanged from your original)
    global disallowed_paths
    disallowed_paths = set()
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            current_ua_is_star = False
            for line in f:
                line = line.strip().lower()
                if not line or line.startswith('#'): continue
                if line.startswith('user-agent:'):
                    current_ua_is_star = (line.split(':', 1)[1].strip() == '*')
                elif line.startswith('disallow:') and current_ua_is_star:
                    rule = line.split(':', 1)[1].strip()
                    if rule: disallowed_paths.add(rule)
        print(f"Loaded {len(disallowed_paths)} Disallow rules from {path}")
    except FileNotFoundError:
        print(f"Warning: robots.txt not found at {path}.")

def is_path_disallowed(path_to_check: str) -> bool:
    """Checks if a given path is disallowed by the loaded rules."""
    # (This function remains unchanged from your original)
    if not path_to_check: return False
    return any(path_to_check.startswith(disallowed) for disallowed in disallowed_paths)

def load_feedback_data() -> Tuple[set, set]:
    """Loads honeypot and CAPTCHA success IPs."""
    # (This function is simplified but functionally equivalent to your original)
    honeypot_triggers: set[str] = set()
    captcha_successes: set[str] = set()
    
    try:
        with open(HONEYPOT_HIT_LOG, 'r') as f:
            for line in f:
                try: honeypot_triggers.add(json.loads(line).get('details', {}).get('ip'))
                except: continue
        print(f"Loaded {len(honeypot_triggers)} IPs from {HONEYPOT_HIT_LOG}")
    except FileNotFoundError:
        print(f"Warning: {HONEYPOT_HIT_LOG} not found.")

    try:
        with open(CAPTCHA_SUCCESS_LOG, 'r') as f:
            for line in f:
                try: captcha_successes.add(line.strip().split(',')[1].strip())
                except: continue
        print(f"Loaded {len(captcha_successes)} IPs from {CAPTCHA_SUCCESS_LOG}")
    except FileNotFoundError:
        print(f"Warning: {CAPTCHA_SUCCESS_LOG} not found.")
        
    return honeypot_triggers, captcha_successes

# --- Labeling ---
def assign_labels_and_scores(df: pd.DataFrame, honeypot_triggers: set, captcha_successes: set) -> pd.DataFrame:
    """Applies your original, sophisticated scoring logic to the DataFrame."""
    print("Assigning labels and scores to the dataset...")
    
    # Helper function to apply your logic to each row
    def calculate_score(row):
        score, reasons = 0.5, []
        ua_lower = row['user_agent'].lower()
        
        # Apply your original scoring logic
        if row['ua_is_known_bad'] and not row['ua_is_known_benign_crawler']:
            score += 0.45; reasons.append("KnownBadUA")
        if row['ua_is_empty']:
            score += 0.30; reasons.append("EmptyUA")
        if row['path_disallowed'] and not row['ua_is_known_benign_crawler']:
            score += 0.35; reasons.append("DisallowedPath")
        if row['status'] > 400:
            score += 0.10; reasons.append(f"ClientError_{row['status']}")
        if row['req_freq_60s'] > 50:
            score += 0.15; reasons.append(f"HighFreq_{int(row['req_freq_60s'])}")
        if row['time_since_last_sec'] != -1 and row['time_since_last_sec'] < 0.5:
            score += 0.10; reasons.append("VeryFastRepeat")
        
        # Apply deductions
        if row['ua_is_known_benign_crawler']:
            score -= 0.60; reasons.append("KnownBenignUA")
        if not row['referer_is_empty']:
            score -= 0.10; reasons.append("HasReferer")

        return max(0.0, min(1.0, score)), reasons

    # Apply scoring to all rows at once
    df[['bot_score', 'labeling_reasons']] = df.apply(calculate_score, axis=1, result_type='expand')

    # Apply final labels based on score and feedback
    df['label'] = 'suspicious'
    df.loc[df['bot_score'] >= 0.8, 'label'] = 'bot'
    df.loc[df['bot_score'] <= 0.2, 'label'] = 'human'
    
    # Override labels based on feedback files (highest priority)
    df.loc[df['ip'].isin(honeypot_triggers), 'label'] = 'bot'
    df.loc[df['ip'].isin(captcha_successes), 'label'] = 'human'
    
    print("Labeling complete. Label distribution:")
    print(df['label'].value_counts())
    
    return df

# --- Model Training and Saving ---
def train_and_save_model(df: pd.DataFrame, model_path: str):
    """Trains a model on high-confidence data."""
    # (This function is adapted to use the DataFrame)
    high_conf_df = df[df['label'].isin(['bot', 'human'])].copy()
    
    if len(high_conf_df) < MIN_SAMPLES_FOR_TRAINING:
        print(f"Skipping RF training: Only {len(high_conf_df)} high-confidence samples, need {MIN_SAMPLES_FOR_TRAINING}.")
        return

    feature_cols = [
        'ua_length', 'status', 'bytes', 'path_depth', 'path_length', 'path_is_root',
        'path_is_wp', 'path_disallowed', 'ua_is_known_bad', 'ua_is_known_benign_crawler',
        'ua_is_empty', 'referer_is_empty', 'hour_of_day', 'day_of_week',
        'req_freq_60s', 'time_since_last_sec'
    ]
    
    high_conf_df['is_bot'] = high_conf_df['label'].apply(lambda x: 1 if x == 'bot' else 0)

    X = high_conf_df[feature_cols]
    y = high_conf_df['is_bot']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    model = RandomForestClassifier(
        n_estimators=150, random_state=42, class_weight='balanced', n_jobs=-1
    )
    model.fit(X_train, y_train)

    print("\n--- RF Model Evaluation ---")
    y_pred = model.predict(X_test)
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print("\nClassification Report:\n", classification_report(y_test, y_pred, target_names=['human', 'bot']))
    
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(model, model_path)
    print(f"Model saved to {model_path}")

def save_data_for_finetuning(df: pd.DataFrame, train_file: str, eval_file: str, eval_ratio: float):
    """Saves high-confidence data in JSONL format for LLM fine-tuning."""
    # (This function is adapted to use the DataFrame)
    print("Preparing and saving data for LLM fine-tuning...")
    finetune_df = df[df['label'].isin(['bot', 'human'])].copy()
    
    if finetune_df.empty:
        print("No high-confidence data to save for fine-tuning.")
        return
        
    train_df, eval_df = train_test_split(finetune_df, test_size=eval_ratio, random_state=42, stratify=finetune_df['label'])

    def write_jsonl(data: pd.DataFrame, file_path: str):
        if not file_path: return
        data_to_write = data.to_dict('records')
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for entry in data_to_write:
                    log_data_for_llm = {k: entry[k] for k in entry if k not in ['label', 'bot_score', 'labeling_reasons', 'timestamp']}
                    output_entry = {"log_data": log_data_for_llm, "label": entry['label']}
                    json.dump(output_entry, f, default=str) # Use default=str for datetime etc.
                    f.write('\n')
            print(f"Saved {len(data)} records for fine-tuning to: {file_path}")
        except Exception as e:
            print(f"ERROR: Failed to save fine-tuning data to {file_path}: {e}")

    write_jsonl(train_df, train_file)
    write_jsonl(eval_df, eval_file)


# --- Main Execution ---
if __name__ == "__main__":
    print("--- Starting Bot Detection Model Training & Data Export (High-Performance Version) ---")
    
    load_robots_txt(ROBOTS_TXT_PATH)
    conn = None
    try:
        conn = setup_database()
        if not conn:
            raise Exception("PostgreSQL Database setup failed. Exiting.")

        # Main data processing pipeline
        df = load_and_process_logs(conn)
        
        if not df.empty:
            honeypot_triggers, captcha_successes = load_feedback_data()
            labeled_df = assign_labels_and_scores(df, honeypot_triggers, captcha_successes)
            
            # Train and save the Random Forest model
            train_and_save_model(labeled_df, MODEL_SAVE_PATH)
            
            # Save data for LLM fine-tuning
            save_data_for_finetuning(labeled_df, FINETUNE_TRAIN_FILE, FINETUNE_EVAL_FILE, FINETUNE_SPLIT_RATIO)
        else:
            print("No log data found in the database. Exiting training process.")

    except Exception as e:
        print(f"An unexpected error occurred in the main process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn and not conn.closed:
            conn.close()
            print("PostgreSQL database connection closed.")
            
    print("--- Training Script Finished ---")