# escalation/escalation_engine.py
# Handles incoming suspicious request metadata, analyzes (using rules, RF model, Redis frequency),
# classifies via API calls (local LLM, external), and escalates via webhook.

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any
import httpx
import os
import datetime
import time
import json
import joblib # For loading the saved RF model
import numpy as np
from urllib.parse import urlparse
import re
import redis # For real-time frequency tracking
import asyncio # For LLM/API call placeholders if needed

# --- Import Shared Metrics Module ---
try:
    from metrics import increment_metric, get_metrics; METRICS_AVAILABLE = True
except ImportError:
    print("Warning: Could not import metrics module.")
    def increment_metric(key: str, value: int = 1):
        pass
    def get_metrics():
        return {}
    METRICS_AVAILABLE = False

# --- Attempt to import user-agents library ---
try:
    from user_agents import parse as ua_parse; UA_PARSER_AVAILABLE = True
except ImportError: UA_PARSER_AVAILABLE = False

# --- Configuration ---
# Service URLs & Keys (Use ENV Variables/Secrets)
WEBHOOK_URL = os.getenv("ESCALATION_WEBHOOK_URL")
LOCAL_LLM_API_URL = os.getenv("LOCAL_LLM_API_URL", "http://localhost:11434/v1/chat/completions") # Default Ollama URL
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "llama3:latest") # Model served by local server
LOCAL_LLM_TIMEOUT = float(os.getenv("LOCAL_LLM_TIMEOUT", 45.0)) # Increased timeout
EXTERNAL_API_URL = os.getenv("EXTERNAL_CLASSIFICATION_API_URL") # e.g., https://api.somebotdetector.com/v1/check
EXTERNAL_API_KEY = os.getenv("EXTERNAL_CLASSIFICATION_API_KEY")
EXTERNAL_API_TIMEOUT = float(os.getenv("EXTERNAL_API_TIMEOUT", 15.0))

# File Paths
RF_MODEL_PATH = "/app/models/bot_detection_rf_model.joblib"
ROBOTS_TXT_PATH = "/app/config/robots.txt"

# Redis Config
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB_FREQUENCY = int(os.getenv("REDIS_DB_FREQUENCY", 3))
FREQUENCY_WINDOW_SECONDS = 300
FREQUENCY_KEY_PREFIX = "freq:"

# Thresholds
HEURISTIC_THRESHOLD_LOW = 0.3
HEURISTIC_THRESHOLD_MEDIUM = 0.6
HEURISTIC_THRESHOLD_HIGH = 0.8

# User Agent Lists
KNOWN_BAD_UAS = ['python-requests', 'curl', 'wget', 'scrapy', 'java/', 'ahrefsbot', 'semrushbot', 'mj12bot', 'dotbot', 'petalbot', 'bytespider', 'gptbot', 'ccbot', 'claude-web', 'google-extended', 'dataprovider', 'purebot', 'scan', 'masscan', 'zgrab', 'nmap']
KNOWN_BENIGN_CRAWLERS_UAS = ['googlebot', 'bingbot', 'slurp', 'duckduckbot', 'baiduspider', 'yandexbot', 'googlebot-image']

# --- Setup Clients & Load Resources ---

# Redis Client for Frequency
FREQUENCY_TRACKING_ENABLED = False; redis_client_freq = None
try:
    redis_pool_freq = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB_FREQUENCY, decode_responses=True)
    redis_client_freq = redis.Redis(connection_pool=redis_pool_freq); redis_client_freq.ping()
    print(f"Connected to Redis for Frequency Tracking (DB: {REDIS_DB_FREQUENCY})"); FREQUENCY_TRACKING_ENABLED = True
except Exception as e: print(f"ERROR: Redis connection failed for Frequency Tracking: {e}")

# Load Robots.txt
disallowed_paths = set();
def load_robots_txt(path):
    global disallowed_paths; disallowed_paths = set();
    try:
        current_ua = None;
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip().lower();
                if not line or line.startswith('#'): continue;
                if line.startswith('user-agent:'): ua = line.split(':', 1)[1].strip(); current_ua = '*' if ua == '*' else None;
                elif line.startswith('disallow:') and current_ua == '*': rule = line.split(':', 1)[1].strip();
                if rule and rule != "/": disallowed_paths.add(rule);
    except FileNotFoundError: print(f"Warning: robots.txt not found at {path}.")
    except Exception as e: print(f"Error loading robots.txt: {e}")
    
def is_path_disallowed(path):
    if not path or not disallowed_paths: return False;
    try:
        for disallowed in disallowed_paths:
            if path.startswith(disallowed): return True;
    except Exception: pass;
    return False

load_robots_txt(ROBOTS_TXT_PATH)

# Load Trained Random Forest Model
model_pipeline = None; MODEL_LOADED = False
try:
    if os.path.exists(RF_MODEL_PATH): model_pipeline = joblib.load(RF_MODEL_PATH); MODEL_LOADED = True; print("RF model loaded.")
    else: print(f"Warning: Model file not found at {RF_MODEL_PATH}.")
except Exception as e: print(f"ERROR: Failed to load RF model: {e}")

# --- Feature Extraction Logic ---
def extract_features(log_entry_dict, freq_features):
    # (Complete function as in previous response - includes basic, path, UA, referer, time, frequency features)
    features = {};
    if not isinstance(log_entry_dict, dict): return {};
    ua_string = log_entry_dict.get('user_agent', ''); referer = log_entry_dict.get('referer', ''); path = log_entry_dict.get('path') or '';
    features['ua_length'] = len(ua_string) if ua_string else 0; features['status_code'] = log_entry_dict.get('status', 0); features['bytes_sent'] = log_entry_dict.get('bytes', 0); features['http_method'] = log_entry_dict.get('method', 'UNKNOWN');
    features['path_depth'] = path.count('/'); features['path_length'] = len(path); features['path_is_root'] = 1 if path == '/' else 0; features['path_has_docs'] = 1 if '/docs' in path else 0; features['path_is_wp'] = 1 if ('/wp-' in path or '/xmlrpc.php' in path) else 0; features['path_disallowed'] = 1 if is_path_disallowed(path) else 0;
    ua_lower = ua_string.lower() if ua_string else ''; features['ua_is_known_bad'] = 1 if any(bad in ua_lower for bad in KNOWN_BAD_UAS) else 0; features['ua_is_known_benign_crawler'] = 1 if any(good in ua_lower for good in KNOWN_BENIGN_CRAWLERS_UAS) else 0; features['ua_is_empty'] = 1 if not ua_string else 0;
    ua_parse_failed = False;
    if UA_PARSER_AVAILABLE and ua_string:
        try: parsed_ua = ua_parse(ua_string); features['ua_browser_family'] = parsed_ua.browser.family or 'Other'; features['ua_os_family'] = parsed_ua.os.family or 'Other'; features['ua_device_family'] = parsed_ua.device.family or 'Other'; features['ua_is_mobile'] = 1 if parsed_ua.is_mobile else 0; features['ua_is_tablet'] = 1 if parsed_ua.is_tablet else 0; features['ua_is_pc'] = 1 if parsed_ua.is_pc else 0; features['ua_is_touch'] = 1 if parsed_ua.is_touch_capable else 0; features['ua_library_is_bot'] = 1 if parsed_ua.is_bot else 0
        except Exception: ua_parse_failed = True
    if not UA_PARSER_AVAILABLE or ua_parse_failed: features['ua_browser_family'] = 'Unknown'; features['ua_os_family'] = 'Unknown'; features['ua_device_family'] = 'Unknown'; features['ua_is_mobile'], features['ua_is_tablet'], features['ua_is_pc'], features['ua_is_touch'] = 0, 0, 0, 0; features['ua_library_is_bot'] = features['ua_is_known_bad']
    features['referer_is_empty'] = 1 if not referer else 0; features['referer_has_domain'] = 0;
    try:
        if referer: parsed_referer = urlparse(referer); features['referer_has_domain'] = 1 if parsed_referer.netloc else 0
    except Exception: pass
    timestamp_iso = log_entry_dict.get('timestamp'); hour, dow = -1, -1
    if timestamp_iso:
        try: ts = datetime.datetime.fromisoformat(timestamp_iso.replace('Z', '+00:00')); hour = ts.hour; dow = ts.weekday()
        except Exception: pass
    features['hour_of_day'] = hour; features['day_of_week'] = dow
    features[f'req_freq_{FREQUENCY_WINDOW_SECONDS}s'] = freq_features.get('count', 0)
    features['time_since_last_sec'] = freq_features.get('time_since', -1.0)
    return features


# --- Real-time Frequency Calculation using Redis ---
def get_realtime_frequency_features(ip: str) -> dict:
    """Gets frequency count and time since last request for an IP from Redis."""
    # (Complete function as in previous response - uses redis_client_freq)
    features = {'count': 0, 'time_since': -1.0};
    if not FREQUENCY_TRACKING_ENABLED or not ip or not redis_client_freq: return features;
    try:
        now_unix = time.time(); window_start_unix = now_unix - FREQUENCY_WINDOW_SECONDS; now_ms_str = f"{now_unix:.6f}"; redis_key = f"{FREQUENCY_KEY_PREFIX}{ip}";
        pipe = redis_client_freq.pipeline(); pipe.zremrangebyscore(redis_key, '-inf', f'({window_start_unix}'); pipe.zadd(redis_key, {now_ms_str: now_unix}); pipe.zcount(redis_key, window_start_unix, now_unix); pipe.zrange(redis_key, -2, -1, withscores=True); pipe.expire(redis_key, FREQUENCY_WINDOW_SECONDS + 60); results = pipe.execute();
        current_count = results[2] if len(results) > 2 and isinstance(results[2], int) else 0; features['count'] = max(0, current_count - 1);
        recent_entries = results[3] if len(results) > 3 and isinstance(results[3], list) else [];
        if len(recent_entries) > 1: last_ts = recent_entries[0][1]; time_diff = now_unix - last_ts; features['time_since'] = round(time_diff, 3);
    except redis.exceptions.RedisError as e: print(f"Warning: Redis error frequency check IP {ip}: {e}"); increment_metric("redis_errors_frequency")
    except Exception as e: print(f"Warning: Unexpected error frequency check IP {ip}: {e}");
    return features


# --- Pydantic Models ---
class RequestMetadata(BaseModel):
    timestamp: str | datetime.datetime
    ip: str
    user_agent: str | None = None
    referer: str | None = None
    path: str | None = None
    headers: Dict[str, str] | None = None
    source: str

# --- FastAPI App ---
app = FastAPI()

# --- Analysis & Classification Functions ---
def run_heuristic_and_model_analysis(metadata: RequestMetadata) -> float:
    """Analyzes metadata using rules, RF model, and Redis frequency."""
    # (Complete function as in previous response - calculates combined score)
    increment_metric("heuristic_checks_run"); rule_score = 0.0; model_score = 0.5; model_used = False; final_score = 0.5;
    frequency_features = get_realtime_frequency_features(metadata.ip); increment_metric(f"req_freq_{FREQUENCY_WINDOW_SECONDS}s", frequency_features['count']);
    log_entry_dict = metadata.model_dump();
    if isinstance(log_entry_dict.get('timestamp'), datetime.datetime): log_entry_dict['timestamp'] = log_entry_dict['timestamp'].isoformat();
    ua = metadata.user_agent.lower() if metadata.user_agent else ""; path = metadata.path or ''; is_known_benign = any(good in ua for good in KNOWN_BENIGN_CRAWLERS_UAS);
    if any(bad in ua for bad in KNOWN_BAD_UAS) and not is_known_benign: rule_score += 0.7;
    if not metadata.user_agent: rule_score += 0.5;
    if is_path_disallowed(path) and not is_known_benign: rule_score += 0.6;
    if frequency_features['count'] > 60 : rule_score += 0.3;
    elif frequency_features['count'] > 30 : rule_score += 0.1;
    if frequency_features['time_since'] != -1.0 and frequency_features['time_since'] < 0.3: rule_score += 0.2;
    if is_known_benign: rule_score -= 0.5;
    rule_score = max(0.0, min(1.0, rule_score));
    if MODEL_LOADED and model_pipeline:
        try:
            features_dict = extract_features(log_entry_dict, frequency_features);
            if features_dict: probabilities = model_pipeline.predict_proba([features_dict])[0]; model_score = probabilities[1]; model_used = True; increment_metric("rf_model_predictions");
            else: print(f"Warning: Could not extract features for RF model (IP: {metadata.ip})")
        except Exception as e: print(f"ERROR: RF model prediction failed: {e}"); increment_metric("rf_model_errors");
    if model_used: final_score = (0.3 * rule_score) + (0.7 * model_score)
    else: final_score = rule_score
    final_score = max(0.0, min(1.0, final_score))
    return final_score


async def classify_with_local_llm_api(metadata: RequestMetadata) -> bool | None:
    """
    Classifies metadata using a configured local LLM via REST API.
    Returns True (Bot), False (Human/Benign), or None (Error/Not configured).
    DEPENDS ON: A running local LLM server (Ollama, LM Studio, etc.) at LOCAL_LLM_API_URL serving LOCAL_LLM_MODEL.
    """
    if not LOCAL_LLM_API_URL or not LOCAL_LLM_MODEL: return None # Skip if not configured
    increment_metric("local_llm_checks_run")
    print(f"Attempting classification for IP {metadata.ip} using local LLM API ({LOCAL_LLM_MODEL})...")

    prompt = f"""Analyze the following request metadata and determine if it likely originates from a malicious bot, a benign crawler (like a search engine), or a human user. Consider the user agent, headers, path, IP address patterns (if available), and referer. Respond ONLY with the word 'MALICIOUS_BOT', 'BENIGN_CRAWLER', or 'HUMAN'.

    Metadata:
    IP: {metadata.ip}
    User-Agent: {metadata.user_agent}
    Path: {metadata.path}
    Referer: {metadata.referer}
    Headers: {json.dumps(metadata.headers)}
    """
    api_payload = { "model": LOCAL_LLM_MODEL, "messages": [{"role": "system", "content": "You are a bot detection system. Respond only with 'MALICIOUS_BOT', 'BENIGN_CRAWLER', or 'HUMAN'."},{"role": "user", "content": prompt}], "temperature": 0.1, "stream": False }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LOCAL_LLM_API_URL, json=api_payload, timeout=LOCAL_LLM_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
            print(f"Local LLM API response: '{content}'")
            if "MALICIOUS_BOT" in content: return True
            elif "HUMAN" in content or "BENIGN_CRAWLER" in content: return False
            else: print(f"Warning: Unexpected classification from local LLM: '{content}'"); increment_metric("local_llm_errors_unexpected_response"); return None
    except httpx.TimeoutException: print(f"Error: Timeout calling local LLM API after {LOCAL_LLM_TIMEOUT}s"); increment_metric("local_llm_errors_timeout"); return None
    except httpx.RequestError as exc: print(f"Error: Request error calling local LLM API: {exc}"); increment_metric("local_llm_errors_request"); return None
    except Exception as e: print(f"Error: Unexpected error processing local LLM API response: {e}"); increment_metric("local_llm_errors_unexpected"); return None


async def classify_with_external_api(metadata: RequestMetadata) -> bool | None:
    """
    Classifies metadata using configured external API.
    Returns True (Bot), False (Human), or None (Error/Not configured).
    DEPENDS ON: A valid EXTERNAL_API_URL and potentially EXTERNAL_API_KEY for a third-party service.
    """
    if not EXTERNAL_API_URL: return None
    increment_metric("external_api_checks_run")
    print(f"Attempting classification for IP {metadata.ip} using External API...")

    external_payload = { # --- ADAPT PAYLOAD TO YOUR SPECIFIC EXTERNAL API ---
        "ipAddress": metadata.ip,
        "userAgent": metadata.user_agent,
        "referer": metadata.referer,
        "requestPath": metadata.path,
        "headers": metadata.headers,
        # Add other required fields by the API
    }
    headers = { 'Content-Type': 'application/json' }
    if EXTERNAL_API_KEY: headers['Authorization'] = f"Bearer {EXTERNAL_API_KEY}" # Example Auth

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(EXTERNAL_API_URL, headers=headers, json=external_payload, timeout=EXTERNAL_API_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            # --- PARSE RESPONSE FROM YOUR SPECIFIC EXTERNAL API ---
            # Example: is_bot = result.get("classification", {}).get("is_bot", False)
            is_bot = result.get("is_bot", None) # Needs to be adapted!
            print(f"External API response: IsBot={is_bot}")
            if isinstance(is_bot, bool):
                increment_metric("external_api_success")
                return is_bot
            else:
                 print("Warning: Unexpected response format from external API.")
                 increment_metric("external_api_errors_unexpected_response")
                 return None
    except httpx.TimeoutException: print(f"Error: Timeout calling external API"); increment_metric("external_api_errors_timeout"); return None
    except httpx.RequestError as exc: print(f"Error: Request error calling external API: {exc}"); increment_metric("external_api_errors_request"); return None
    except Exception as e: print(f"Error: Unexpected error processing external API response: {e}"); increment_metric("external_api_errors_unexpected"); return None


# --- Webhook Forwarding (Implemented) ---
async def forward_to_webhook(payload: Dict[str, Any], reason: str):
    """Sends data to the configured webhook URL."""
    if not WEBHOOK_URL: return
    increment_metric("webhooks_sent")
    serializable_payload = json.loads(json.dumps(payload, default=str))
    webhook_payload = { "event_type": "suspicious_activity_detected", "reason": reason, "timestamp_utc": datetime.datetime.utcnow().isoformat()+"Z", "details": serializable_payload }
    headers = {'Content-Type': 'application/json'}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(WEBHOOK_URL, headers=headers, json=webhook_payload, timeout=10.0)
            response.raise_for_status()
    except httpx.RequestError as exc: print(f"Error forwarding to webhook {WEBHOOK_URL}: {exc}"); increment_metric("webhook_errors_request")
    except Exception as e: print(f"Unexpected error during webhook forwarding: {e}"); increment_metric("webhook_errors_unexpected")


# --- API Endpoint (/escalate) ---
@app.post("/escalate")
async def handle_escalation(metadata: RequestMetadata, request: Request):
    """Receives request metadata, performs analysis, and triggers actions."""
    # (Complete function logic remains the same as previous version - uses combined score and calls classification/webhook)
    client_ip = request.client.host if request.client else "unknown"; increment_metric("escalation_requests_received");
    action_taken = "analysis_complete"; is_bot_decision = None;
    combined_score = run_heuristic_and_model_analysis(metadata);
    if combined_score >= HEURISTIC_THRESHOLD_HIGH:
        is_bot_decision = True; action_taken = "webhook_triggered_high_score"; increment_metric("bots_detected_high_score")
        await forward_to_webhook(metadata.model_dump(mode='json'), f"High Combined Score ({combined_score:.3f})")
    elif HEURISTIC_THRESHOLD_LOW <= combined_score < HEURISTIC_THRESHOLD_HIGH:
        local_llm_result = await classify_with_local_llm_api(metadata)
        if local_llm_result is True: is_bot_decision = True; action_taken = "webhook_triggered_local_llm"; increment_metric("bots_detected_local_llm"); await forward_to_webhook(metadata.model_dump(mode='json'), "Local LLM Classification")
        elif local_llm_result is False: is_bot_decision = False; action_taken = "classified_human_local_llm"; increment_metric("humans_detected_local_llm")
        else:
             action_taken = "local_llm_inconclusive"
             if EXTERNAL_API_URL:
                 external_api_result = await classify_with_external_api(metadata)
                 if external_api_result is True: is_bot_decision = True; action_taken = "webhook_triggered_external_api"; increment_metric("bots_detected_external_api"); await forward_to_webhook(metadata.model_dump(mode='json'), "External API Classification")
                 elif external_api_result is False: is_bot_decision = False; action_taken = "classified_human_external_api"; increment_metric("humans_detected_external_api")
                 else: action_taken = "external_api_inconclusive"
    else: is_bot_decision = False; action_taken = "classified_human_low_score"; increment_metric("humans_detected_low_score")
    log_msg = f"IP={metadata.ip}, Source={metadata.source}, Score={combined_score:.3f}, Decision={is_bot_decision}, Action={action_taken}"
    print(f"Escalation Complete: {log_msg}")
    return {"status": "processed", "action": action_taken, "is_bot_decision": is_bot_decision, "score": round(combined_score, 3)}


# --- Metrics Endpoint ---
@app.get("/metrics")
async def get_metrics_endpoint():
    # (Function remains the same)
    if not METRICS_AVAILABLE: raise HTTPException(status_code=501, detail="Metrics module not available")
    return get_metrics()


# --- Main ---
if __name__ == "__main__":
    import uvicorn
    print(f"--- Escalation Engine Starting ---")
    if MODEL_LOADED: print(f"Loaded RF Model from: {RF_MODEL_PATH}")
    else: print(f"WARNING: RF Model NOT loaded from {RF_MODEL_PATH}. Using rule-based heuristics only.")
    if FREQUENCY_TRACKING_ENABLED: print(f"Redis Frequency Tracking Enabled (DB: {REDIS_DB_FREQUENCY})")
    else: print(f"WARNING: Redis Frequency Tracking DISABLED.")
    if not disallowed_paths: print(f"WARNING: No robots.txt rules loaded from {ROBOTS_TXT_PATH}.")
    print(f"Local LLM API configured: {'Yes (' + LOCAL_LLM_API_URL + ')' if LOCAL_LLM_API_URL else 'No'}")
    print(f"External API URL configured: {'Yes (' + EXTERNAL_API_URL + ')' if EXTERNAL_API_URL else 'No'}")
    print(f"Webhook URL configured: {'Yes (' + WEBHOOK_URL + ')' if WEBHOOK_URL else 'No'}")
    print(f"---------------------------------")
    uvicorn.run(app, host="0.0.0.0", port=8003)