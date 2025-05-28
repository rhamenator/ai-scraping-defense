# rag/training.py
# Parses Apache logs, loads into SQLite DB, labels entries with scores,
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
import sqlite3

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
DB_PATH = os.getenv("TRAINING_DB_PATH", "/app/data/log_analysis.db")
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
KNOWN_BAD_UAS = [ua.strip() for ua in os.getenv("KNOWN_BAD_UAS", 'python-requests,curl,wget,scrapy,java/,ahrefsbot,semrushbot,mj12bot,dotbot,petalbot,bytespider,gptbot,ccbot,claude-web,google-extended,dataprovider,purebot,scan,masscan,zgrab,nmap').split(',') if ua.strip()]
KNOWN_BENIGN_CRAWLERS_UAS = [ua.strip() for ua in os.getenv("KNOWN_BENIGN_CRAWLERS_UAS", 'googlebot,bingbot,slurp,duckduckbot,baiduspider,yandexbot,googlebot-image').split(',') if ua.strip()]

# --- SQLite Database Setup ---
def setup_database(db_path):
    # (Complete function as in previous response)
    print(f"Setting up database at: {db_path}"); os.makedirs(os.path.dirname(db_path), exist_ok=True); conn = None;
    try:
        conn = sqlite3.connect(db_path); cursor = conn.cursor();
        cursor.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT NOT NULL, ident TEXT, user TEXT, timestamp_iso TEXT NOT NULL, method TEXT, path TEXT, protocol TEXT, status INTEGER, bytes INTEGER, referer TEXT, user_agent TEXT)');
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ip_timestamp ON requests (ip, timestamp_iso)'); cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON requests (timestamp_iso)');
        conn.commit(); print("Database table 'requests' verified."); return conn
    except Exception as e: print(f"ERROR: Database setup failed: {e}"); conn.close() if conn else None; return None

# --- Robots.txt Parsing ---
disallowed_paths = set();
def load_robots_txt(path): # (Complete function as in previous response)
    global disallowed_paths; disallowed_paths = set();
    try:
        current_ua = None;
        rule = None
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip().lower();
                if not line or line.startswith('#'): continue;
                if line.startswith('user-agent:'): ua = line.split(':', 1)[1].strip(); current_ua = '*' if ua == '*' else None;
                elif line.startswith('disallow:') and current_ua == '*': rule = line.split(':', 1)[1].strip();
                if rule and rule != "/": disallowed_paths.add(rule);
        # print(f"Loaded {len(disallowed_paths)} Disallow rules from {path}")
    except FileNotFoundError: print(f"Warning: robots.txt not found at {path}.")
    except Exception as e: print(f"Error loading robots.txt: {e}")
def is_path_disallowed(path): # (Complete function as in previous response)
    if not path or not disallowed_paths: return False;
    try:
        for disallowed in disallowed_paths:
            if path.startswith(disallowed): return True;
    except Exception: pass;
    return False
load_robots_txt(ROBOTS_TXT_PATH)

# --- Log Parsing & Loading into DB ---
def parse_apache_combined_log_line(line): # (Complete function as in previous response)
    pattern = re.compile(r'^(?P<ip>\S+) (?P<ident>\S+) (?P<user>\S+) \[(?P<timestamp>.+?)\] 'r'"(?P<request>.*?)" (?P<status>\d{3}|-) (?P<bytes>\S+) 'r'"(?P<referer>.*?)" "(?P<user_agent>.*?)"$'); match = pattern.match(line);
    if match:
        data = match.groupdict(); data['ident'] = None if data['ident'] == '-' else data['ident']; data['user'] = None if data['user'] == '-' else data['user']; data['status'] = int(data['status']) if data['status'] != '-' else 0; data['bytes'] = int(data['bytes']) if data['bytes'] != '-' else 0; data['referer'] = None if data['referer'] == '-' else data['referer']; data['user_agent'] = None if data['user_agent'] in ('-', '') else data['user_agent'];
        try: timestamp_obj = datetime.datetime.strptime(data['timestamp'], '%d/%b/%Y:%H:%M:%S %z'); data['timestamp'] = timestamp_obj.astimezone(datetime.timezone.utc); data['timestamp_iso'] = data['timestamp'].isoformat(timespec='seconds');
        except (ValueError, TypeError): return None;
        req_parts = data['request'].split();
        if len(req_parts) >= 2: data['method'] = req_parts[0]; data['path'] = req_parts[1]; data['protocol'] = req_parts[2] if len(req_parts) > 2 else None;
        else: data['method'], data['path'], data['protocol'] = 'INVALID', data['request'], None;
        if 'timestamp' in data: del data['timestamp'];
        return data
    return None
def load_logs_into_db(log_path, conn): # (Complete function as in previous response)
    print(f"Loading logs from {log_path} into database..."); cursor = conn.cursor(); inserted_count = 0; line_count = 0; parse_errors = 0; insert_errors = 0; batch_size = 1000; batch = [];
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_count += 1; parsed = parse_apache_combined_log_line(line.strip());
                if parsed:
                    data_tuple = (parsed.get('ip'), parsed.get('ident'), parsed.get('user'), parsed.get('timestamp_iso'), parsed.get('method'), parsed.get('path'), parsed.get('protocol'), parsed.get('status'), parsed.get('bytes'), parsed.get('referer'), parsed.get('user_agent')); batch.append(data_tuple);
                    if len(batch) >= batch_size:
                        try: cursor.executemany('INSERT INTO requests (...) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', batch); conn.commit(); inserted_count += len(batch); batch = [];
                        except sqlite3.Error as e: print(f"ERROR: DB insert error: {e}"); insert_errors += len(batch); batch = [];
                else: parse_errors += 1;
            if batch:
                try: cursor.executemany('INSERT INTO requests (...) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', batch); conn.commit(); inserted_count += len(batch);
                except sqlite3.Error as e: print(f"ERROR: DB insert error (final batch): {e}"); insert_errors += len(batch);
    except FileNotFoundError: print(f"ERROR: Log file not found at {log_path}"); return False;
    except Exception as e: print(f"ERROR: Failed to read/parse log file {log_path}: {e}"); return False;
    print(f"DB loading complete. Lines: {line_count}, ParsedErrs: {parse_errors}, Inserted: {inserted_count}, InsertErrs: {insert_errors}"); return inserted_count > 0

# --- Feature Engineering ---
def extract_features_from_db(log_entry_row, db_cursor): # (Complete function as in previous response)
    col_names = [desc[0] for desc in db_cursor.description]; log_entry_dict = dict(zip(col_names, log_entry_row)); features = {};
    ua_string = log_entry_dict.get('user_agent', ''); referer = log_entry_dict.get('referer', ''); path = log_entry_dict.get('path') or ''; ip = log_entry_dict.get('ip'); current_timestamp_iso = log_entry_dict.get('timestamp_iso');
    features['ua_length'] = len(ua_string) if ua_string else 0; features['status_code'] = log_entry_dict.get('status', 0); features['bytes_sent'] = log_entry_dict.get('bytes', 0); features['http_method'] = log_entry_dict.get('method', 'UNKNOWN');
    features['path_depth'] = path.count('/'); features['path_length'] = len(path); features['path_is_root'] = 1 if path == '/' else 0; features['path_has_docs'] = 1 if '/docs' in path else 0; features['path_is_wp'] = 1 if ('/wp-' in path or '/xmlrpc.php' in path) else 0; features['path_disallowed'] = 1 if is_path_disallowed(path) else 0;
    ua_lower = ua_string.lower() if ua_string else ''; features['ua_is_known_bad'] = 1 if any(bad in ua_lower for bad in KNOWN_BAD_UAS) else 0; features['ua_is_known_benign_crawler'] = 1 if any(good in ua_lower for good in KNOWN_BENIGN_CRAWLERS_UAS) else 0; features['ua_is_empty'] = 1 if not ua_string else 0;
    ua_parse_failed = False;
    if UA_PARSER_AVAILABLE and callable(ua_parse) and ua_string:
        try: parsed_ua = ua_parse(ua_string); features['ua_browser_family'] = parsed_ua.browser.family or 'Other'; features['ua_os_family'] = parsed_ua.os.family or 'Other'; features['ua_device_family'] = parsed_ua.device.family or 'Other'; features['ua_is_mobile'] = 1 if parsed_ua.is_mobile else 0; features['ua_is_tablet'] = 1 if parsed_ua.is_tablet else 0; features['ua_is_pc'] = 1 if parsed_ua.is_pc else 0; features['ua_is_touch'] = 1 if parsed_ua.is_touch_capable else 0; features['ua_library_is_bot'] = 1 if parsed_ua.is_bot else 0
        except Exception: ua_parse_failed = True
    if not UA_PARSER_AVAILABLE or not callable(ua_parse) or ua_parse_failed: features['ua_browser_family'] = 'Unknown'; features['ua_os_family'] = 'Unknown'; features['ua_device_family'] = 'Unknown'; features['ua_is_mobile'], features['ua_is_tablet'], features['ua_is_pc'], features['ua_is_touch'] = 0, 0, 0, 0; features['ua_library_is_bot'] = features['ua_is_known_bad']
    features['referer_is_empty'] = 1 if not referer else 0; features['referer_has_domain'] = 0;
    try:
        if referer: parsed_referer = urlparse(referer); features['referer_has_domain'] = 1 if parsed_referer.netloc else 0
    except Exception: pass
    hour, dow = -1, -1;
    if current_timestamp_iso:
        try: ts = datetime.datetime.fromisoformat(current_timestamp_iso.replace('Z', '+00:00')); hour = ts.hour; dow = ts.weekday()
        except Exception: pass
    features['hour_of_day'] = hour; features['day_of_week'] = dow
    # Frequency/Timing Features (Querying DB)
    req_freq = 0; time_since = -1.0;
    if ip and current_timestamp_iso:
        try:
            current_time_dt = datetime.datetime.fromisoformat(current_timestamp_iso.replace('Z', '+00:00')); window_start_dt = current_time_dt - datetime.timedelta(seconds=FREQUENCY_WINDOW_SECONDS); window_start_iso = window_start_dt.isoformat(timespec='seconds');
            db_cursor.execute("SELECT COUNT(*) FROM requests WHERE ip = ? AND timestamp_iso >= ? AND timestamp_iso < ?", (ip, window_start_iso, current_timestamp_iso)); result = db_cursor.fetchone(); req_freq = result[0] if result else 0;
            db_cursor.execute("SELECT MAX(timestamp_iso) FROM requests WHERE ip = ? AND timestamp_iso < ?", (ip, current_timestamp_iso)); result = db_cursor.fetchone();
            if result and result[0]: last_time_dt = datetime.datetime.fromisoformat(result[0].replace('Z', '+00:00')); time_diff = (current_time_dt - last_time_dt).total_seconds(); time_since = round(time_diff, 3);
        except Exception as e: print(f"Warning: Error calculating frequency features (IP: {ip}): {e}")
    features[f'req_freq_{FREQUENCY_WINDOW_SECONDS}s'] = req_freq; features['time_since_last_sec'] = time_since;
    return features

# --- Labeling (with Scoring / Confidence) ---
def load_feedback_data():
    """Loads honeypot hits and CAPTCHA successes from configured log files."""
    honeypot_triggers = set(); captcha_successes = set(); print("Loading feedback data...")
    # --- Load Honeypot Hits ---
    # Assumes JSON format from shared/honeypot_logger.py: {"timestamp": "...", "details": {"ip": "..."}}
    try:
        with open(HONEYPOT_HIT_LOG, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                try:
                    log_data = json.loads(line)
                    ip = log_data.get('details', {}).get('ip')
                    if ip: honeypot_triggers.add(ip)
                except json.JSONDecodeError: print(f"Warning: Skipping invalid JSON in {HONEYPOT_HIT_LOG} line {line_num+1}")
                except Exception as e_inner: print(f"Warning: Error processing line {line_num+1} in {HONEYPOT_HIT_LOG}: {e_inner}")
        print(f"Loaded {len(honeypot_triggers)} unique IPs from {HONEYPOT_HIT_LOG}")
    except FileNotFoundError: print(f"Warning: File not found {HONEYPOT_HIT_LOG}. No honeypot feedback.")
    except Exception as e: print(f"Error loading {HONEYPOT_HIT_LOG}: {e}")

    # --- Load CAPTCHA Successes ---
    # Assumes simple CSV format: timestamp,ip_or_session_id,... (adapt if different)
    try:
        with open(CAPTCHA_SUCCESS_LOG, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                try:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        identifier = parts[1].strip() # Assume IP/Session is the second field
                        if identifier: captcha_successes.add(identifier)
                    # else: print(f"Warning: Skipping malformed line in {CAPTCHA_SUCCESS_LOG} line {line_num+1}") # Optional
                except Exception as e_inner: print(f"Warning: Error processing line {line_num+1} in {CAPTCHA_SUCCESS_LOG}: {e_inner}")
        print(f"Loaded {len(captcha_successes)} unique IPs/Sessions from {CAPTCHA_SUCCESS_LOG}")
    except FileNotFoundError: print(f"Warning: File not found {CAPTCHA_SUCCESS_LOG}. No CAPTCHA feedback.")
    except Exception as e: print(f"Error loading {CAPTCHA_SUCCESS_LOG}: {e}")

    # --- Add logic here to load from Redis if needed ---
    # Example:
    # try:
    #    import redis
    #    r = redis.Redis(...)
    #    for key in r.scan_iter(f"honeypot_hit:*"): honeypot_triggers.add(key.split(":")[-1])
    #    # ... similar for captcha ...
    #    r.close()
    # except Exception as e: print(f"Error loading feedback from Redis: {e}")

    return honeypot_triggers, captcha_successes

def assign_label_and_score(log_entry_dict, honeypot_triggers, captcha_successes):
    # (Complete scoring logic from previous version)
    ip = log_entry_dict.get('ip'); feedback_key = ip; ua_lower = (log_entry_dict.get('user_agent') or '').lower(); path = log_entry_dict.get('path') or ''; status = log_entry_dict.get('status', 0); method = log_entry_dict.get('method', '');
    score = 0.5; reasons = [];
    if feedback_key in captcha_successes: return 'human', 0.05, ["CAPTCHA_Success"];
    if feedback_key in honeypot_triggers: return 'bot', 0.98, ["Honeypot_Hit"];
    is_known_benign = any(good in ua_lower for good in KNOWN_BENIGN_CRAWLERS_UAS); is_known_bad = any(bad in ua_lower for bad in KNOWN_BAD_UAS);
    if is_known_bad and not is_known_benign: score += 0.45; reasons.append("KnownBadUA");
    if not log_entry_dict.get('user_agent'): score += 0.30; reasons.append("EmptyUA");
    if is_path_disallowed(path) and not is_known_benign: score += 0.35; reasons.append("DisallowedPath");
    if status == 403 and is_path_disallowed(path): score += 0.15; reasons.append("Disallowed403");
    if status >= 500: score += 0.15; reasons.append("ServerErrors");
    if status == 404 and path.count('/') > 5: score += 0.10; reasons.append("Deep404");
    if method not in ['GET', 'POST', 'HEAD', 'OPTIONS']: score += 0.10; reasons.append("UncommonMethod");
    if log_entry_dict.get('referer') is None and not path.endswith(('.css', '.js', '.png', '.ico')) and path != '/': score += 0.05; reasons.append("MissingRefererNonAsset");
    req_freq = log_entry_dict.get(f'req_freq_{FREQUENCY_WINDOW_SECONDS}s', 0); time_since = log_entry_dict.get('time_since_last_sec', -1.0);
    if req_freq > 50: score += 0.15; reasons.append(f"HighFreq_{req_freq}");
    elif req_freq > 20: score += 0.05; reasons.append(f"MedFreq_{req_freq}");
    if time_since != -1.0 and time_since < 0.5: score += 0.10; reasons.append("VeryFastRepeat");
    if is_known_benign: score -= 0.60; reasons.append("KnownBenignUA");
    if log_entry_dict.get('referer') and urlparse(log_entry_dict.get('referer')).netloc: score -= 0.10; reasons.append("HasReferer");
    if status >= 200 and status < 300 and method == 'GET': score -= 0.05; reasons.append("GoodGET");
    if path.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.woff2')): score -= 0.05; reasons.append("StaticAsset");
    if UA_PARSER_AVAILABLE and not is_known_benign and not is_known_bad:
        try:
            if ua_parse and callable(ua_parse):
                try:
                    if ua_parse(log_entry_dict.get('user_agent')).is_bot:
                        score += 0.20
                        reasons.append("UALibBotFlag")
                except Exception:
                    pass
        except Exception: pass;
    score = max(0.0, min(1.0, score));
    if score >= 0.80: label = 'bot';
    elif score <= 0.20: label = 'human';
    else: label = 'suspicious';
    return label, score, reasons

def label_data_with_scores(db_conn):
    """Queries DB, extracts features, assigns labels/scores."""
    print("Processing & labeling data from database...")
    honeypot_triggers, captcha_successes = load_feedback_data()
    labeled_data = []
    high_conf_features = []
    high_conf_labels = []
    label_counts = defaultdict(int)
    processed_count = 0
    db_cursor = db_conn.cursor()

    try:
        db_cursor.execute("SELECT * FROM requests ORDER BY timestamp_iso") # Process chronologically
        while True:
            rows = db_cursor.fetchmany(10000) # Process in chunks
            if not rows: break

            for row in rows:
                processed_count += 1
                # Convert row tuple to dict for labeling function
                col_names = [desc[0] for desc in db_cursor.description]
                log_entry_dict = dict(zip(col_names, row))

                # Extract features first (calculates frequency based on DB state *before* this row)
                features_dict = extract_features_from_db(row, db_cursor) # Pass row tuple and cursor

                # Add frequency features to log_entry_dict for labeling function
                log_entry_dict[f'req_freq_{FREQUENCY_WINDOW_SECONDS}s'] = features_dict.get(f'req_freq_{FREQUENCY_WINDOW_SECONDS}s', 0)
                log_entry_dict['time_since_last_sec'] = features_dict.get('time_since_last_sec', -1.0)

                # Assign label and score using the enriched dict
                label, score, reasons = assign_label_and_score(log_entry_dict, honeypot_triggers, captcha_successes)

                # Store results
                log_entry_dict['label'] = label
                log_entry_dict['bot_score'] = round(score, 3)
                log_entry_dict['labeling_reasons'] = reasons
                labeled_data.append(log_entry_dict) # Store full labeled dict
                label_counts[label] += 1

                # Store features/labels for high-confidence samples for RF training
                if label in ['bot', 'human']:
                    high_conf_features.append(features_dict) # Store extracted features
                    high_conf_labels.append(1 if label == 'bot' else 0) # Store binary label

            print(f"Processed {processed_count} log entries...")

    except sqlite3.Error as e:
        print(f"ERROR: Database error during data processing: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected error during data processing: {e}")
        import traceback; traceback.print_exc()
    finally:
         db_cursor.close() # Close cursor when done

    print(f"Finished processing. Label counts: {dict(label_counts)}")
    total_labeled = len(labeled_data)
    total_high_conf = len(high_conf_features)
    print(f"Total entries processed: {total_labeled}")
    print(f"High-confidence ('bot'/'human') samples for RF training: {total_high_conf}")

    if total_high_conf < MIN_SAMPLES_FOR_TRAINING:
         print(f"Warning: Insufficient high-confidence labeled data ({total_high_conf}) for reliable RF training.")

    return labeled_data, high_conf_features, high_conf_labels


# --- Model Training & Saving (Random Forest) ---
def train_and_save_model(training_data_features, training_labels, model_path):
    # (Complete function as in previous version)
     if not training_data_features or len(training_data_features) < MIN_SAMPLES_FOR_TRAINING: print("Skipping RF training..."); return None
     if len(training_data_features) != len(training_labels): print("ERROR: Feature/label length mismatch..."); return None
     print(f"Starting RF model training with {len(training_data_features)} samples...")
     X_train, X_test, y_train, y_test = train_test_split(training_data_features, training_labels, test_size=0.25, random_state=42, stratify=training_labels)
     pipeline = Pipeline([('vectorizer', DictVectorizer(sparse=False)), ('classifier', RandomForestClassifier(n_estimators=150, random_state=42, class_weight='balanced', n_jobs=-1, max_depth=25, min_samples_split=10, min_samples_leaf=5))])
     start_time = time.time(); pipeline.fit(X_train, y_train); end_time = time.time()
     print(f"RF Model training completed in {end_time - start_time:.2f} seconds.")
     print("\n--- RF Model Evaluation ---"); y_pred = pipeline.predict(X_test); y_prob = pipeline.predict_proba(X_test)[:, 1]
     print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
     try: print(f"AUC: {roc_auc_score(y_test, y_prob):.4f}")
     except ValueError as e: print(f"Could not calculate AUC: {e}")
     print("\nClassification Report:\n", classification_report(y_test, y_pred, target_names=['human', 'bot']))
     print("---------------------------")
     print(f"Saving RF model pipeline to {model_path}...")
     try: os.makedirs(os.path.dirname(model_path), exist_ok=True); joblib.dump(pipeline, model_path); print("RF Model saved successfully.")
     except Exception as e: print(f"ERROR: Failed to save RF model: {e}")
     return pipeline

# --- Save Data for Fine-tuning ---
def save_data_for_finetuning(all_labeled_data, train_file, eval_file, eval_ratio=0.15):
    # (Complete function as in previous version - saves JSONL)
    print("Preparing and saving data for LLM fine-tuning...");
    high_conf_bot = [d for d in all_labeled_data if d.get('label') == 'bot' and d.get('bot_score', 0) >= 0.85]; high_conf_human = [d for d in all_labeled_data if d.get('label') == 'human' and d.get('bot_score', 1) <= 0.15];
    finetune_data = high_conf_bot + high_conf_human; print(f"Found {len(finetune_data)} high-confidence samples ({len(high_conf_bot)} bot, {len(high_conf_human)} human) for fine-tuning.");
    if not finetune_data: print("No high-confidence data found."); return;
    random.shuffle(finetune_data); split_index = int(len(finetune_data) * (1 - eval_ratio)); train_data = finetune_data[:split_index]; eval_data = finetune_data[split_index:];
    print(f"Splitting into {len(train_data)} training and {len(eval_data)} evaluation samples."); os.makedirs(os.path.dirname(train_file), exist_ok=True);
    def write_jsonl(data, file_path):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for entry in data:
                    log_data_copy = {k: v for k, v in entry.items() if k not in ['label', 'bot_score', 'labeling_reasons', 'timestamp']}; log_data_copy['timestamp_iso'] = entry.get('timestamp_iso');
                    output_entry = {"log_data": log_data_copy, "label": entry['label']}; json.dump(output_entry, f); f.write('\n');
            print(f"Saved data for fine-tuning to: {file_path}")
        except Exception as e: print(f"ERROR: Failed to save fine-tuning data to {file_path}: {e}")
    write_jsonl(train_data, train_file); write_jsonl(eval_data, eval_file);

# --- Main Execution ---
if __name__ == "__main__":
    print("--- Starting Bot Detection Model Training & Data Export ---")
    db_conn = None
    try:
        # 1. Setup Database
        db_conn = setup_database(DB_PATH)
        if not db_conn: raise Exception("Database setup failed")

        # 2. Load Logs into DB (Conditional)
        db_cursor_check = db_conn.cursor(); db_cursor_check.execute("SELECT COUNT(*) FROM requests");
        if db_cursor_check.fetchone()[0] == 0: load_logs_into_db(LOG_FILE_PATH, db_conn)
        else: print("Database already contains data. Skipping log loading.")
        db_cursor_check.close()

        # 3. Process Data from DB, Label, Extract Features
        all_labeled_logs, high_conf_features, high_conf_labels = label_data_with_scores(db_conn)

        # 4. Train Random Forest Model
        if high_conf_features:
             model = train_and_save_model(high_conf_features, high_conf_labels, MODEL_SAVE_PATH)
        else: print("Skipping RF model training due to insufficient data.")

        # 5. Save Data for LLM Fine-tuning
        save_data_for_finetuning(all_labeled_logs, FINETUNE_TRAIN_FILE, FINETUNE_EVAL_FILE)

        # 6. Analyze 'suspicious' data (Optional)
        suspicious_logs = [log for log in all_labeled_logs if log['label'] == 'suspicious']
        print(f"\nFound {len(suspicious_logs)} entries labeled 'suspicious'. Consider manual review.")

    except Exception as e: print(f"An unexpected error occurred in the main process: {e}"); import traceback; traceback.print_exc();
    finally:
        if db_conn: db_conn.close(); print("Database connection closed.");
    print("--- Training Script Finished ---")