# rag/training.py
# Parses Apache logs, loads into PostgreSQL DB, labels entries with scores,
# extracts features (incl. frequency from DB), trains RandomForest,
# AND saves data in JSONL format for LLM fine-tuning.

import pandas as pd
import re
import datetime
from collections import defaultdict, deque
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
import psycopg2 # Changed from sqlite3
from psycopg2.extras import execute_batch # For efficient batch inserts
from typing import Optional, Dict, Any, List, Tuple # Added missing imports

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

# PostgreSQL Connection Environment Variables
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
FREQUENCY_WINDOW_SECONDS = int(os.getenv("TRAINING_FREQ_WINDOW_SEC", 300))

# Ensure KNOWN_BAD_UAS and KNOWN_BENIGN_CRAWLERS_UAS are always lists
KNOWN_BAD_UAS_STR = os.getenv("KNOWN_BAD_UAS", 'python-requests,curl,wget,scrapy,java/,ahrefsbot,semrushbot,mj12bot,dotbot,petalbot,bytespider,gptbot,ccbot,claude-web,google-extended,dataprovider,purebot,scan,masscan,zgrab,nmap')
KNOWN_BAD_UAS = [ua.strip().lower() for ua in KNOWN_BAD_UAS_STR.split(',') if ua.strip()]

KNOWN_BENIGN_CRAWLERS_UAS_STR = os.getenv("KNOWN_BENIGN_CRAWLERS_UAS", 'googlebot,bingbot,slurp,duckduckbot,baiduspider,yandexbot,googlebot-image')
KNOWN_BENIGN_CRAWLERS_UAS = [ua.strip().lower() for ua in KNOWN_BENIGN_CRAWLERS_UAS_STR.split(',') if ua.strip()]


# --- PostgreSQL Database Setup ---
def _get_pg_password(password_file_path: str) -> Optional[str]:
    """Loads password from secret file."""
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
    """Sets up PostgreSQL database and creates table if not exists."""
    print(f"Setting up PostgreSQL database: {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}")
    # Ensure model and finetune data directories exist
    if MODEL_SAVE_PATH: os.makedirs(os.path.dirname(MODEL_SAVE_PATH), exist_ok=True)
    if FINETUNE_DATA_DIR: os.makedirs(FINETUNE_DATA_DIR, exist_ok=True)


    conn = None
    pg_password = _get_pg_password(PG_PASSWORD_FILE)
    if not pg_password:
        print(f"Error: PostgreSQL password not found via PG_PASSWORD_FILE: {PG_PASSWORD_FILE}. Cannot connect.")
        return None

    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DBNAME,
            user=PG_USER,
            password=pg_password,
            connect_timeout=10
        )
        conn.autocommit = False
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                ip TEXT NOT NULL,
                ident TEXT,
                user_text TEXT,
                timestamp_iso TEXT NOT NULL,
                method TEXT,
                path TEXT,
                protocol TEXT,
                status INTEGER,
                bytes INTEGER,
                referer TEXT,
                user_agent TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_requests_ip_timestamp ON requests (ip, timestamp_iso)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests (timestamp_iso)')
        conn.commit()
        cursor.close()
        print("PostgreSQL database table 'requests' verified.")
        return conn
    except psycopg2.Error as e:
        print(f"ERROR: PostgreSQL database setup failed: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error during PostgreSQL setup: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return None

# --- Robots.txt Parsing ---
disallowed_paths: set[str] = set() # Type hint for clarity
def load_robots_txt(path: str):
    global disallowed_paths
    disallowed_paths = set()
    rule = None
    current_ua_is_star = False
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip().lower()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('user-agent:'):
                    ua_spec = line.split(':', 1)[1].strip()
                    current_ua_is_star = (ua_spec == '*')
                elif line.startswith('disallow:') and current_ua_is_star:
                    rule = line.split(':', 1)[1].strip()
                    if rule and rule != "/": # Add rule if not empty and not just "/"
                        disallowed_paths.add(rule)
        print(f"Loaded {len(disallowed_paths)} Disallow rules for User-agent: * from {path}")
    except FileNotFoundError:
        print(f"Warning: robots.txt not found at {path}.")
    except Exception as e:
        print(f"Error loading robots.txt from {path}: {e}")

def is_path_disallowed(path_to_check: str) -> bool:
    if not path_to_check or not disallowed_paths:
        return False
    try:
        for disallowed in disallowed_paths:
            if path_to_check.startswith(disallowed):
                return True
    except Exception: # Catch any unexpected error during path checking
        pass
    return False

if ROBOTS_TXT_PATH: load_robots_txt(ROBOTS_TXT_PATH)


# --- Log Parsing & Loading into DB ---
def parse_apache_combined_log_line(line: str) -> Optional[Dict[str, Any]]:
    pattern = re.compile(
        r'^(?P<ip>\S+) (?P<ident>\S+) (?P<user>\S+) \[(?P<timestamp>.+?)\] '
        r'"(?P<request>.*?)" (?P<status>\d{3}|-) (?P<bytes>\S+) '
        r'"(?P<referer>.*?)" "(?P<user_agent>.*?)"$'
    )
    match = pattern.match(line)
    if match:
        data = match.groupdict()
        data['ident'] = None if data['ident'] == '-' else data['ident']
        data['user_text'] = None if data['user'] == '-' else data['user'] # Renamed
        del data['user'] # Remove original 'user' key
        data['status'] = int(data['status']) if data['status'] != '-' else 0
        data['bytes'] = int(data['bytes']) if data['bytes'] != '-' else 0
        data['referer'] = None if data['referer'] == '-' else data['referer']
        data['user_agent'] = None if data['user_agent'] in ('-', '') else data['user_agent']
        try:
            timestamp_obj = datetime.datetime.strptime(data['timestamp'], '%d/%b/%Y:%H:%M:%S %z')
            # Store as UTC ISO string
            data['timestamp_iso'] = timestamp_obj.astimezone(datetime.timezone.utc).isoformat(timespec='seconds')
        except (ValueError, TypeError):
            return None # Invalid timestamp format
        
        req_parts = data['request'].split()
        if len(req_parts) >= 2:
            data['method'] = req_parts[0]
            data['path'] = req_parts[1]
            data['protocol'] = req_parts[2] if len(req_parts) > 2 else None
        else: # Malformed request string
            data['method'], data['path'], data['protocol'] = 'INVALID', data['request'], None
        
        if 'timestamp' in data: del data['timestamp'] # Remove original timestamp string
        return data
    return None

def load_logs_into_db(log_path: str, conn: psycopg2.extensions.connection) -> bool:
    print(f"Loading logs from {log_path} into PostgreSQL database...")
    inserted_count = 0
    line_count = 0
    parse_errors = 0
    insert_errors = 0
    batch_size = 1000
    batch: List[tuple] = [] # Type hint for batch
    cursor = None # Initialize cursor to None

    insert_sql = '''
        INSERT INTO requests (ip, ident, user_text, timestamp_iso, method, path, protocol, status, bytes, referer, user_agent)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    '''
    try:
        cursor = conn.cursor()
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_count += 1
                parsed = parse_apache_combined_log_line(line.strip())
                if parsed:
                    data_tuple = (
                        parsed.get('ip'), parsed.get('ident'), parsed.get('user_text'),
                        parsed.get('timestamp_iso'), parsed.get('method'), parsed.get('path'),
                        parsed.get('protocol'), parsed.get('status'), parsed.get('bytes'),
                        parsed.get('referer'), parsed.get('user_agent')
                    )
                    batch.append(data_tuple)

                    if len(batch) >= batch_size:
                        try:
                            execute_batch(cursor, insert_sql, batch)
                            conn.commit()
                            inserted_count += len(batch)
                            print(f"DB Load: Committed batch of {len(batch)}. Total inserted: {inserted_count}")
                            batch = []
                        except psycopg2.Error as e:
                            print(f"ERROR: PostgreSQL DB insert error: {e}")
                            conn.rollback()
                            insert_errors += len(batch)
                            batch = []
                        except Exception as e_gen:
                            print(f"ERROR: Unexpected error during batch insert: {e_gen}")
                            conn.rollback()
                            insert_errors += len(batch)
                            batch = []
                else:
                    parse_errors += 1
                
                if line_count % 50000 == 0:
                     print(f"DB Load: Processed {line_count} lines from log file...")

            if batch:
                try:
                    execute_batch(cursor, insert_sql, batch)
                    conn.commit()
                    inserted_count += len(batch)
                    print(f"DB Load: Committed final batch of {len(batch)}. Total inserted: {inserted_count}")
                except psycopg2.Error as e:
                    print(f"ERROR: PostgreSQL DB insert error (final batch): {e}")
                    conn.rollback()
                    insert_errors += len(batch)
                except Exception as e_gen:
                    print(f"ERROR: Unexpected error during final batch insert: {e_gen}")
                    conn.rollback()
                    insert_errors += len(batch)
    except FileNotFoundError:
        print(f"ERROR: Log file not found at {log_path}")
        return False
    except psycopg2.Error as e:
        print(f"ERROR: PostgreSQL connection or cursor error during log loading: {e}")
        if conn: conn.rollback()
        return False
    except Exception as e:
        print(f"ERROR: Failed to read/parse log file {log_path}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if cursor and not cursor.closed: # Check if cursor was initialized and not closed
            cursor.close()

    print(f"PostgreSQL DB loading complete. Lines: {line_count}, ParsedErrs: {parse_errors}, Inserted: {inserted_count}, InsertErrs: {insert_errors}")
    return inserted_count > 0


# --- Feature Engineering ---
def extract_features_from_db(log_entry_row_tuple: tuple, col_names: List[str], db_cursor: psycopg2.extensions.cursor) -> Dict[str, Any]:
    features: Dict[str, Any] = {}
    log_entry_dict = dict(zip(col_names, log_entry_row_tuple))

    ua_string = log_entry_dict.get('user_agent', '') or ''
    referer = log_entry_dict.get('referer', '') or ''
    path = log_entry_dict.get('path', '') or ''
    ip = log_entry_dict.get('ip')
    current_timestamp_iso = log_entry_dict.get('timestamp_iso')

    features['ua_length'] = len(ua_string)
    features['status_code'] = log_entry_dict.get('status', 0)
    features['bytes_sent'] = log_entry_dict.get('bytes', 0)
    features['http_method'] = log_entry_dict.get('method', 'UNKNOWN')
    features['path_depth'] = path.count('/')
    features['path_length'] = len(path)
    features['path_is_root'] = 1 if path == '/' else 0
    features['path_has_docs'] = 1 if '/docs' in path.lower() else 0
    features['path_is_wp'] = 1 if ('/wp-' in path or '/xmlrpc.php' in path) else 0
    features['path_disallowed'] = 1 if is_path_disallowed(path) else 0

    ua_lower = ua_string.lower() # ua_string is guaranteed to be a string here
    features['ua_is_known_bad'] = 1 if any(bad in ua_lower for bad in KNOWN_BAD_UAS) else 0
    features['ua_is_known_benign_crawler'] = 1 if any(good in ua_lower for good in KNOWN_BENIGN_CRAWLERS_UAS) else 0
    features['ua_is_empty'] = 1 if not ua_string else 0

    ua_parse_failed = False
    if UA_PARSER_AVAILABLE and callable(ua_parse) and ua_string:
        try:
            parsed_ua = ua_parse(ua_string)
            features['ua_browser_family'] = parsed_ua.browser.family or 'Other'
            features['ua_os_family'] = parsed_ua.os.family or 'Other'
            features['ua_device_family'] = parsed_ua.device.family or 'Other'
            features['ua_is_mobile'] = 1 if parsed_ua.is_mobile else 0
            features['ua_is_tablet'] = 1 if parsed_ua.is_tablet else 0
            features['ua_is_pc'] = 1 if parsed_ua.is_pc else 0
            features['ua_is_touch'] = 1 if parsed_ua.is_touch_capable else 0
            features['ua_library_is_bot'] = 1 if parsed_ua.is_bot else 0
        except Exception:
            ua_parse_failed = True

    if not UA_PARSER_AVAILABLE or not callable(ua_parse) or ua_parse_failed:
        features['ua_browser_family'] = 'Unknown'
        features['ua_os_family'] = 'Unknown'
        features['ua_device_family'] = 'Unknown'
        features['ua_is_mobile'], features['ua_is_tablet'], features['ua_is_pc'], features['ua_is_touch'] = 0,0,0,0
        features['ua_library_is_bot'] = features['ua_is_known_bad']

    features['referer_is_empty'] = 1 if not referer else 0
    features['referer_has_domain'] = 0
    try:
        if referer:
            parsed_referer = urlparse(referer)
            features['referer_has_domain'] = 1 if parsed_referer.netloc else 0
    except Exception:
        pass

    hour, dow = -1, -1
    if current_timestamp_iso:
        try:
            ts = datetime.datetime.fromisoformat(current_timestamp_iso.replace('Z', '+00:00'))
            hour = ts.hour
            dow = ts.weekday()
        except Exception:
            pass
    features['hour_of_day'] = hour
    features['day_of_week'] = dow

    req_freq = 0
    time_since_last = -1.0
    if ip and current_timestamp_iso:
        try:
            current_time_dt = datetime.datetime.fromisoformat(current_timestamp_iso.replace('Z', '+00:00'))
            window_start_dt = current_time_dt - datetime.timedelta(seconds=FREQUENCY_WINDOW_SECONDS)
            window_start_iso_pg = window_start_dt.isoformat(sep=' ')
            current_timestamp_iso_pg = current_time_dt.isoformat(sep=' ')

            db_cursor.execute(
                "SELECT COUNT(*) FROM requests WHERE ip = %s AND timestamp_iso >= %s AND timestamp_iso < %s",
                (ip, window_start_iso_pg, current_timestamp_iso_pg)
            )
            result_freq = db_cursor.fetchone()
            req_freq = result_freq[0] if result_freq else 0

            db_cursor.execute(
                "SELECT MAX(timestamp_iso) FROM requests WHERE ip = %s AND timestamp_iso < %s",
                (ip, current_timestamp_iso_pg)
            )
            result_last_ts = db_cursor.fetchone()
            if result_last_ts and result_last_ts[0]:
                last_time_dt = datetime.datetime.fromisoformat(result_last_ts[0].replace('Z', '+00:00'))
                time_diff_seconds = (current_time_dt - last_time_dt).total_seconds()
                time_since_last = round(time_diff_seconds, 3)
        except psycopg2.Error as e:
            print(f"Warning: PostgreSQL error calculating frequency features for IP {ip}: {e}")
        except Exception as e_gen:
            print(f"Warning: Generic error calculating frequency for IP {ip}: {e_gen}")

    features[f'req_freq_{FREQUENCY_WINDOW_SECONDS}s'] = req_freq
    features['time_since_last_sec'] = time_since_last
    return features

# --- Labeling (with Scoring / Confidence) ---
def load_feedback_data() -> Tuple[set, set]:
    honeypot_triggers: set[str] = set()
    captcha_successes: set[str] = set()
    print("Loading feedback data...")
    try:
        with open(HONEYPOT_HIT_LOG, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                try:
                    log_data = json.loads(line)
                    ip = log_data.get('details', {}).get('ip')
                    if ip: honeypot_triggers.add(ip)
                except json.JSONDecodeError: print(f"W: Skipping JSON in {HONEYPOT_HIT_LOG} L{line_num+1}")
                except Exception as e_inner: print(f"W: Error processing {HONEYPOT_HIT_LOG} L{line_num+1}: {e_inner}")
        print(f"Loaded {len(honeypot_triggers)} IPs from {HONEYPOT_HIT_LOG}")
    except FileNotFoundError: print(f"W: {HONEYPOT_HIT_LOG} not found.")
    except Exception as e: print(f"E: loading {HONEYPOT_HIT_LOG}: {e}")
    
    try:
        with open(CAPTCHA_SUCCESS_LOG, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                identifier = None # Initialize identifier
                try:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        identifier = parts[1].strip()
                        if identifier: captcha_successes.add(identifier)
                except Exception as e_inner: print(f"W: Error processing {CAPTCHA_SUCCESS_LOG} L{line_num+1} (id: {identifier}): {e_inner}")
        print(f"Loaded {len(captcha_successes)} IPs/Sessions from {CAPTCHA_SUCCESS_LOG}")
    except FileNotFoundError: print(f"W: {CAPTCHA_SUCCESS_LOG} not found.")
    except Exception as e: print(f"E: loading {CAPTCHA_SUCCESS_LOG}: {e}")
    return honeypot_triggers, captcha_successes

def assign_label_and_score(log_entry_dict: Dict[str, Any], honeypot_triggers: set, captcha_successes: set) -> Tuple[str, float, List[str]]:
    ip = log_entry_dict.get('ip')
    feedback_key = ip
    ua_string = log_entry_dict.get('user_agent', '') or '' # Ensures ua_string is not None
    ua_lower = ua_string.lower()
    path = log_entry_dict.get('path', '') or ''
    status = log_entry_dict.get('status', 0)
    method = log_entry_dict.get('method', '')
    
    score = 0.5
    reasons: List[str] = []

    if feedback_key in captcha_successes: return 'human', 0.05, ["CAPTCHA_Success"]
    if feedback_key in honeypot_triggers: return 'bot', 0.98, ["Honeypot_Hit"]

    is_known_benign = any(good in ua_lower for good in KNOWN_BENIGN_CRAWLERS_UAS)
    is_known_bad = any(bad in ua_lower for bad in KNOWN_BAD_UAS)

    if is_known_bad and not is_known_benign: score += 0.45; reasons.append("KnownBadUA")
    if not ua_string: score += 0.30; reasons.append("EmptyUA") # Check ua_string itself
    if is_path_disallowed(path) and not is_known_benign: score += 0.35; reasons.append("DisallowedPath")
    if status == 403 and is_path_disallowed(path): score += 0.15; reasons.append("Disallowed403")
    if status >= 500: score += 0.15; reasons.append("ServerErrors")
    if status == 404 and path.count('/') > 5: score += 0.10; reasons.append("Deep404")
    if method not in ['GET', 'POST', 'HEAD', 'OPTIONS']: score += 0.10; reasons.append("UncommonMethod")
    if log_entry_dict.get('referer') is None and not path.endswith(('.css', '.js', '.png', '.ico')) and path != '/': score += 0.05; reasons.append("MissingRefererNonAsset")
    
    req_freq = log_entry_dict.get(f'req_freq_{FREQUENCY_WINDOW_SECONDS}s', 0)
    time_since = log_entry_dict.get('time_since_last_sec', -1.0)
    if req_freq > 50: score += 0.15; reasons.append(f"HighFreq_{req_freq}")
    elif req_freq > 20: score += 0.05; reasons.append(f"MedFreq_{req_freq}")
    if time_since != -1.0 and time_since < 0.5: score += 0.10; reasons.append("VeryFastRepeat")
    
    if is_known_benign: score -= 0.60; reasons.append("KnownBenignUA")
    if log_entry_dict.get('referer') and urlparse(str(log_entry_dict.get('referer', ''))).netloc: score -= 0.10; reasons.append("HasReferer") # Ensure referer is string for urlparse
    if status >= 200 and status < 300 and method == 'GET': score -= 0.05; reasons.append("GoodGET")
    if path.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.woff2')): score -= 0.05; reasons.append("StaticAsset")
    
    if UA_PARSER_AVAILABLE and not is_known_benign and not is_known_bad:
        try:
            if ua_parse and callable(ua_parse) and ua_string:
                if ua_parse(ua_string).is_bot: # ua_string is guaranteed to be string
                    score += 0.20; reasons.append("UALibBotFlag")
        except Exception: pass
    
    score = max(0.0, min(1.0, score))
    label = 'suspicious'
    if score >= 0.80: label = 'bot'
    elif score <= 0.20: label = 'human'
    return label, score, reasons

def label_data_with_scores(db_conn: psycopg2.extensions.connection) -> Tuple[List[Dict[str,Any]], List[Dict[str,Any]], List[int]]:
    print("Processing & labeling data from PostgreSQL database...")
    honeypot_triggers, captcha_successes = load_feedback_data()
    labeled_data: List[Dict[str, Any]] = []
    high_conf_features: List[Dict[str, Any]] = []
    high_conf_labels: List[int] = []
    label_counts = defaultdict(int)
    processed_count = 0
    db_cursor = None

    try:
        db_cursor = db_conn.cursor(name="training_cursor")
        db_cursor.execute("SELECT id, ip, ident, user_text, timestamp_iso, method, path, protocol, status, bytes, referer, user_agent FROM requests ORDER BY timestamp_iso")
        
        # Check if cursor.description is None (robustness for an unlikely scenario)
        if db_cursor.description is None:
            print("CRITICAL ERROR: db_cursor.description is None after query execution. Table schema might be missing or query failed silently.")
            return [], [], []
        col_names = [desc[0] for desc in db_cursor.description]


        while True:
            rows = db_cursor.fetchmany(10000)
            if not rows: break

            for row_tuple in rows:
                processed_count += 1
                current_row_dict_for_labeling = dict(zip(col_names, row_tuple))
                
                with db_conn.cursor() as lookup_cursor: # Use a new cursor for sub-queries
                    features_dict = extract_features_from_db(row_tuple, col_names, lookup_cursor)

                current_row_dict_for_labeling[f'req_freq_{FREQUENCY_WINDOW_SECONDS}s'] = features_dict.get(f'req_freq_{FREQUENCY_WINDOW_SECONDS}s', 0)
                current_row_dict_for_labeling['time_since_last_sec'] = features_dict.get('time_since_last_sec', -1.0)

                label, score, reasons = assign_label_and_score(current_row_dict_for_labeling, honeypot_triggers, captcha_successes)

                current_row_dict_for_labeling['label'] = label
                current_row_dict_for_labeling['bot_score'] = round(score, 3)
                current_row_dict_for_labeling['labeling_reasons'] = reasons
                labeled_data.append(current_row_dict_for_labeling)
                label_counts[label] += 1

                if label in ['bot', 'human']:
                    high_conf_features.append(features_dict)
                    high_conf_labels.append(1 if label == 'bot' else 0)
                
                if processed_count % 10000 == 0:
                     print(f"LabelData: Processed {processed_count} log entries...")

    except psycopg2.Error as e:
        print(f"ERROR: PostgreSQL database error during data processing: {e}")
        if db_conn and not db_conn.closed: db_conn.rollback()
    except Exception as e:
        print(f"ERROR: Unexpected error during data processing: {e}")
        import traceback; traceback.print_exc()
    finally:
        if db_cursor and not db_cursor.closed:
            db_cursor.close()

    print(f"Finished processing. Label counts: {dict(label_counts)}")
    total_labeled = len(labeled_data)
    total_high_conf = len(high_conf_features)
    print(f"Total entries processed for labeling: {total_labeled}")
    print(f"High-confidence ('bot'/'human') samples for RF training: {total_high_conf}")

    if total_high_conf < MIN_SAMPLES_FOR_TRAINING:
        print(f"Warning: Insufficient high-confidence labeled data ({total_high_conf}) for reliable RF training. Target: {MIN_SAMPLES_FOR_TRAINING}")
    return labeled_data, high_conf_features, high_conf_labels

# --- Model Training & Saving (Random Forest) ---
def train_and_save_model(training_data_features: List[Dict[str, Any]], training_labels: List[int], model_path: str) -> Optional[Pipeline]:
    if not training_data_features or len(training_data_features) < MIN_SAMPLES_FOR_TRAINING:
        print(f"Skipping RF training: Only {len(training_data_features)} samples, need {MIN_SAMPLES_FOR_TRAINING}.")
        return None
    if len(training_data_features) != len(training_labels):
        print(f"ERROR: Feature ({len(training_data_features)}) and label ({len(training_labels)}) length mismatch. Cannot train model.")
        return None
    
    unique_labels = set(training_labels)
    if len(unique_labels) < 2:
        print(f"Warning: Only one class ({unique_labels}) present in training data. Skipping RF training as it's not meaningful.")
        return None

    print(f"Starting RF model training with {len(training_data_features)} samples...")
    stratify_option = training_labels if len(training_labels) >= 2 * 2 and len(unique_labels) >=2 else None

    X_train, X_test, y_train, y_test = train_test_split(
        training_data_features, training_labels,
        test_size=0.25, random_state=42,
        stratify=stratify_option
    )
    pipeline = Pipeline([
        ('vectorizer', DictVectorizer(sparse=False)),
        ('classifier', RandomForestClassifier(
            n_estimators=150, random_state=42, class_weight='balanced',
            n_jobs=-1, max_depth=25, min_samples_split=10, min_samples_leaf=5
        ))
    ])
    start_time = time.time(); pipeline.fit(X_train, y_train); end_time = time.time()
    print(f"RF Model training completed in {end_time - start_time:.2f} seconds.")
    print("\n--- RF Model Evaluation ---"); y_pred = pipeline.predict(X_test)
    
    if len(set(y_test)) > 1:
        y_prob = pipeline.predict_proba(X_test)[:, 1]
        try: print(f"AUC: {roc_auc_score(y_test, y_prob):.4f}")
        except ValueError as e: print(f"Could not calculate AUC (possibly only one class in y_test): {e}")
    else: print("AUC not calculated: Only one class in y_test.")

    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print("\nClassification Report:\n", classification_report(y_test, y_pred, target_names=['human', 'bot'], zero_division=0))
    print("---------------------------")
    print(f"Saving RF model pipeline to {model_path}...")
    try:
        if model_path: os.makedirs(os.path.dirname(model_path), exist_ok=True)
        joblib.dump(pipeline, model_path)
        print("RF Model saved successfully.")
    except Exception as e: print(f"ERROR: Failed to save RF model: {e}")
    return pipeline

# --- Save Data for Fine-tuning ---
def save_data_for_finetuning(all_labeled_data: List[Dict[str, Any]], train_file: str, eval_file: str, eval_ratio: float = 0.15):
    print("Preparing and saving data for LLM fine-tuning...")
    high_conf_bot = [d for d in all_labeled_data if d.get('label') == 'bot' and d.get('bot_score', 0) >= 0.85]
    high_conf_human = [d for d in all_labeled_data if d.get('label') == 'human' and d.get('bot_score', 1) <= 0.15]

    finetune_data = high_conf_bot + high_conf_human
    print(f"Found {len(finetune_data)} high-confidence samples ({len(high_conf_bot)} bot, {len(high_conf_human)} human) for fine-tuning.")

    if not finetune_data: print("No high-confidence data found for fine-tuning."); return

    random.shuffle(finetune_data)
    split_index = int(len(finetune_data) * (1 - eval_ratio))
    train_data = finetune_data[:split_index]
    eval_data = finetune_data[split_index:]

    print(f"Splitting for fine-tuning: {len(train_data)} training and {len(eval_data)} evaluation samples.")
    if train_file: os.makedirs(os.path.dirname(train_file), exist_ok=True)
    if eval_file: os.makedirs(os.path.dirname(eval_file), exist_ok=True)


    def write_jsonl(data_list: List[Dict[str, Any]], file_path: str):
        if not file_path: print(f"Warning: File path for JSONL is empty, skipping write."); return
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for entry in data_list:
                    log_data_for_llm = {
                        k: v for k, v in entry.items()
                        if k not in ['label', 'bot_score', 'labeling_reasons', 'id', 'timestamp']
                    }
                    if 'timestamp_iso' not in log_data_for_llm and 'timestamp_iso' in entry:
                        log_data_for_llm['timestamp_iso'] = entry['timestamp_iso']
                    output_entry = {"log_data": log_data_for_llm, "label": entry['label']}
                    json.dump(output_entry, f)
                    f.write('\n')
            print(f"Saved data for fine-tuning to: {file_path}")
        except Exception as e:
            print(f"ERROR: Failed to save fine-tuning data to {file_path}: {e}")

    write_jsonl(train_data, train_file)
    write_jsonl(eval_data, eval_file)

# --- Main Execution ---
if __name__ == "__main__":
    print("--- Starting Bot Detection Model Training & Data Export (PostgreSQL Version) ---")
    db_conn = None
    try:
        db_conn = setup_database()
        if not db_conn:
            raise Exception("PostgreSQL Database setup failed. Exiting.")

        db_cursor_check = db_conn.cursor()
        db_cursor_check.execute("SELECT COUNT(*) FROM requests")
        count_result = db_cursor_check.fetchone() # Fetch the result first
        initial_row_count = count_result[0] if count_result else 0 # Then check and subscript
        db_cursor_check.close()

        if initial_row_count == 0:
            print("PostgreSQL 'requests' table is empty. Loading logs...")
            if not load_logs_into_db(LOG_FILE_PATH, db_conn): # Pass LOG_FILE_PATH
                print("Log loading failed.") # Further action might be needed
        else:
            print(f"PostgreSQL 'requests' table already contains {initial_row_count} rows. Skipping log loading.")

        all_labeled_logs, high_conf_features, high_conf_labels = label_data_with_scores(db_conn)

        if high_conf_features and high_conf_labels:
            model = train_and_save_model(high_conf_features, high_conf_labels, MODEL_SAVE_PATH)
        else:
            print("Skipping RF model training due to insufficient or inconsistent high-confidence data.")

        save_data_for_finetuning(all_labeled_logs, FINETUNE_TRAIN_FILE, FINETUNE_EVAL_FILE)

        suspicious_logs = [log for log in all_labeled_logs if log.get('label') == 'suspicious']
        print(f"\nFound {len(suspicious_logs)} entries labeled 'suspicious'. Consider manual review or further analysis.")

    except psycopg2.Error as db_err:
        print(f"A PostgreSQL database error occurred in the main process: {db_err}")
        if db_conn and not db_conn.closed : db_conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred in the main process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print("PostgreSQL database connection closed.")
    print("--- Training Script Finished ---")
