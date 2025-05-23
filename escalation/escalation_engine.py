# escalation/escalation_engine.py
# Handles incoming suspicious request metadata, analyzes (using rules, RF model, IP Rep, Redis frequency),
# classifies via API calls (local LLM, external), potentially triggers CAPTCHA, and escalates via webhook.

from fastapi import FastAPI, Request, HTTPException, Response # Added Response
from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Any, Optional # Added Optional
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
import logging # Added for better logging

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Import Shared Metrics Module ---
try:
    from metrics import increment_metric, get_metrics; METRICS_AVAILABLE = True
except ImportError:
    logger.warning("Could not import metrics module.")
    def increment_metric(key: str, value: int = 1): pass
    def get_metrics(): return {}
    METRICS_AVAILABLE = False

# --- Attempt to import user-agents library ---
try:
    from user_agents import parse as ua_parse; UA_PARSER_AVAILABLE = True
except ImportError:
    UA_PARSER_AVAILABLE = False
    logger.warning("user-agents library not found. Detailed UA parsing disabled.")

# --- Configuration ---
# Service URLs & Keys (Use ENV Variables/Secrets)
WEBHOOK_URL = os.getenv("ESCALATION_WEBHOOK_URL") # To AI Service
LOCAL_LLM_API_URL = os.getenv("LOCAL_LLM_API_URL")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL")
LOCAL_LLM_TIMEOUT = float(os.getenv("LOCAL_LLM_TIMEOUT", 45.0))
EXTERNAL_API_URL = os.getenv("EXTERNAL_CLASSIFICATION_API_URL")
EXTERNAL_API_KEY_FILE = os.getenv("EXTERNAL_CLASSIFICATION_API_KEY_FILE", "/run/secrets/external_api_key")
EXTERNAL_API_TIMEOUT = float(os.getenv("EXTERNAL_API_TIMEOUT", 15.0))

# IP Reputation Config (NEW)
ENABLE_IP_REPUTATION = os.getenv("ENABLE_IP_REPUTATION", "false").lower() == "true"
IP_REPUTATION_API_URL = os.getenv("IP_REPUTATION_API_URL")
IP_REPUTATION_API_KEY_FILE = os.getenv("IP_REPUTATION_API_KEY_FILE", "/run/secrets/ip_reputation_api_key")
IP_REPUTATION_TIMEOUT = float(os.getenv("IP_REPUTATION_TIMEOUT", 10.0))
IP_REPUTATION_MALICIOUS_SCORE_BONUS = float(os.getenv("IP_REPUTATION_MALICIOUS_SCORE_BONUS", 0.3))
IP_REPUTATION_MIN_MALICIOUS_THRESHOLD = float(os.getenv("IP_REPUTATION_MIN_MALICIOUS_THRESHOLD", 50)) # Example threshold

# CAPTCHA Trigger Config (NEW - Hooks only)
ENABLE_CAPTCHA_TRIGGER = os.getenv("ENABLE_CAPTCHA_TRIGGER", "false").lower() == "true"
CAPTCHA_SCORE_THRESHOLD_LOW = float(os.getenv("CAPTCHA_SCORE_THRESHOLD_LOW", 0.2))
CAPTCHA_SCORE_THRESHOLD_HIGH = float(os.getenv("CAPTCHA_SCORE_THRESHOLD_HIGH", 0.5))
CAPTCHA_VERIFICATION_URL = os.getenv("CAPTCHA_VERIFICATION_URL") # URL to redirect user for CAPTCHA

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

# --- Load Secrets ---
def load_secret(file_path: Optional[str]) -> Optional[str]:
    """Loads a secret from a file."""
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Failed to read secret from {file_path}: {e}")
    return None

EXTERNAL_API_KEY = load_secret(EXTERNAL_API_KEY_FILE)
IP_REPUTATION_API_KEY = load_secret(IP_REPUTATION_API_KEY_FILE)

# --- Setup Clients & Load Resources ---

# Redis Client for Frequency
FREQUENCY_TRACKING_ENABLED = False; redis_client_freq = None
try:
    redis_pool_freq = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB_FREQUENCY, decode_responses=True)
    redis_client_freq = redis.Redis(connection_pool=redis_pool_freq)
    redis_client_freq.ping()
    logger.info(f"Connected to Redis for Frequency Tracking (DB: {REDIS_DB_FREQUENCY})")
    FREQUENCY_TRACKING_ENABLED = True
except redis.exceptions.ConnectionError as e:
    logger.error(f"Redis connection failed for Frequency Tracking: {e}. Tracking disabled.")
except Exception as e:
    logger.error(f"Unexpected error connecting to Redis for Frequency Tracking: {e}. Tracking disabled.")

# Load Robots.txt
disallowed_paths = set()
def load_robots_txt(path):
    global disallowed_paths; disallowed_paths = set()
    try:
        current_ua = None;
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip().lower();
                if not line or line.startswith('#'): continue;
                if line.startswith('user-agent:'): ua = line.split(':', 1)[1].strip(); current_ua = '*' if ua == '*' else None;
                elif line.startswith('disallow:') and current_ua == '*': rule = line.split(':', 1)[1].strip();
                if rule and rule != "/": disallowed_paths.add(rule);
    except FileNotFoundError: logger.warning(f"robots.txt not found at {path}.")
    except Exception as e: logger.error(f"Error loading robots.txt from {path}: {e}")

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
    if os.path.exists(RF_MODEL_PATH):
        model_pipeline = joblib.load(RF_MODEL_PATH)
        MODEL_LOADED = True
        logger.info(f"RF model loaded successfully from {RF_MODEL_PATH}.")
    else:
        logger.warning(f"Model file not found at {RF_MODEL_PATH}. Heuristic scoring only.")
except Exception as e:
    logger.error(f"Failed to load RF model from {RF_MODEL_PATH}: {e}")

# --- Feature Extraction Logic ---
# (Ensure this remains identical to the one used in training.py)
def extract_features(log_entry_dict, freq_features):
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
    # Placeholder for potential future features
    # features['ip_rep_score'] = ip_rep_result.get('score', -1)
    # features['anomaly_score'] = anomaly_result.get('score', 0)
    return features

# --- Real-time Frequency Calculation using Redis ---
def get_realtime_frequency_features(ip: str) -> dict:
    """Gets frequency count and time since last request for an IP from Redis."""
    features = {'count': 0, 'time_since': -1.0};
    if not FREQUENCY_TRACKING_ENABLED or not ip or not redis_client_freq: return features;
    try:
        now_unix = time.time(); window_start_unix = now_unix - FREQUENCY_WINDOW_SECONDS; now_ms_str = f"{now_unix:.6f}"; redis_key = f"{FREQUENCY_KEY_PREFIX}{ip}";
        pipe = redis_client_freq.pipeline();
        pipe.zremrangebyscore(redis_key, '-inf', f'({window_start_unix}');
        pipe.zadd(redis_key, {now_ms_str: now_unix});
        pipe.zcount(redis_key, window_start_unix, now_unix);
        pipe.zrange(redis_key, -2, -1, withscores=True);
        pipe.expire(redis_key, FREQUENCY_WINDOW_SECONDS + 60);
        results = pipe.execute();
        current_count = results[2] if len(results) > 2 and isinstance(results[2], int) else 0;
        features['count'] = max(0, current_count - 1);
        recent_entries = results[3] if len(results) > 3 and isinstance(results[3], list) else [];
        if len(recent_entries) > 1:
            last_ts = recent_entries[0][1]; time_diff = now_unix - last_ts;
            features['time_since'] = round(time_diff, 3);
    except redis.exceptions.RedisError as e: logger.warning(f"Redis error frequency check IP {ip}: {e}"); increment_metric("redis_errors_frequency")
    except Exception as e: logger.warning(f"Unexpected error frequency check IP {ip}: {e}");
    return features

# --- IP Reputation Check (NEW) ---
async def check_ip_reputation(ip: str) -> Optional[Dict[str, Any]]:
    """Checks IP reputation using a configured external service."""
    if not ENABLE_IP_REPUTATION or not IP_REPUTATION_API_URL or not ip:
        return None
    increment_metric("ip_reputation_checks_run")
    logger.info(f"Checking IP reputation for {ip} using {IP_REPUTATION_API_URL}")

    # --- Adapt this section based on the specific API you use ---
    # Example using a generic placeholder API structure
    headers = {'Accept': 'application/json'}
    params = {'ipAddress': ip}
    if IP_REPUTATION_API_KEY:
        headers['Authorization'] = f"Bearer {IP_REPUTATION_API_KEY}" # Or other auth method

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(IP_REPUTATION_API_URL, params=params, headers=headers, timeout=IP_REPUTATION_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"IP Reputation API response for {ip}: {result}")

            # --- Parse the specific API response ---
            # Example parsing (adjust based on actual API response):
            is_malicious = False
            score = result.get("abuseConfidenceScore", 0) # Example field from AbuseIPDB
            # Check if score exceeds threshold
            if score >= IP_REPUTATION_MIN_MALICIOUS_THRESHOLD:
                is_malicious = True
            # You might also check other fields like 'isTor', 'isProxy', 'threats', etc.

            increment_metric("ip_reputation_success")
            if is_malicious: increment_metric("ip_reputation_malicious")
            return {"is_malicious": is_malicious, "score": score, "raw_response": result} # Return useful info

    except httpx.TimeoutException: logger.error(f"Timeout checking IP reputation for {ip}"); increment_metric("ip_reputation_errors_timeout"); return None
    except httpx.RequestError as exc: logger.error(f"Request error checking IP reputation for {ip}: {exc}"); increment_metric("ip_reputation_errors_request"); return None
    except json.JSONDecodeError as exc: logger.error(f"JSON decode error processing IP reputation response for {ip}: {exc} - Response: {response.text[:500]}"); increment_metric("ip_reputation_errors_response_decode"); return None
    except Exception as e: logger.error(f"Unexpected error checking IP reputation for {ip}: {e}", exc_info=True); increment_metric("ip_reputation_errors_unexpected"); return None


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
app = FastAPI(title="Escalation Engine", description="Analyzes suspicious requests and escalates if necessary.")

# --- Analysis & Classification Functions ---
def run_heuristic_and_model_analysis(metadata: RequestMetadata, ip_rep_result: Optional[Dict] = None) -> float:
    """Analyzes metadata using rules, RF model, Redis frequency, and optional IP reputation."""
    increment_metric("heuristic_checks_run"); rule_score = 0.0; model_score = 0.5; model_used = False; final_score = 0.5;
    frequency_features = get_realtime_frequency_features(metadata.ip); increment_metric(f"req_freq_{FREQUENCY_WINDOW_SECONDS}s", frequency_features['count']);
    log_entry_dict = metadata.model_dump();
    if isinstance(log_entry_dict.get('timestamp'), datetime.datetime): log_entry_dict['timestamp'] = log_entry_dict['timestamp'].isoformat();

    # --- Apply Heuristics ---
    ua = metadata.user_agent.lower() if metadata.user_agent else ""; path = metadata.path or ''; is_known_benign = any(good in ua for good in KNOWN_BENIGN_CRAWLERS_UAS);
    if any(bad in ua for bad in KNOWN_BAD_UAS) and not is_known_benign: rule_score += 0.7;
    if not metadata.user_agent: rule_score += 0.5;
    if is_path_disallowed(path) and not is_known_benign: rule_score += 0.6;
    if frequency_features['count'] > 60 : rule_score += 0.3;
    elif frequency_features['count'] > 30 : rule_score += 0.1;
    if frequency_features['time_since'] != -1.0 and frequency_features['time_since'] < 0.3: rule_score += 0.2;
    if is_known_benign: rule_score -= 0.5; # Significantly reduce score for known good bots
    rule_score = max(0.0, min(1.0, rule_score));

    # --- Apply RF Model ---
    if MODEL_LOADED and model_pipeline:
        try:
            # Extract features, including frequency
            # Placeholder: Add ip_rep_score feature if model is retrained with it
            features_dict = extract_features(log_entry_dict, frequency_features);
            if features_dict:
                probabilities = model_pipeline.predict_proba([features_dict])[0];
                model_score = probabilities[1]; # Probability of class '1' (bot)
                model_used = True;
                increment_metric("rf_model_predictions");
            else: logger.warning(f"Could not extract features for RF model (IP: {metadata.ip})")
        except Exception as e: logger.error(f"RF model prediction failed for IP {metadata.ip}: {e}"); increment_metric("rf_model_errors");

    # --- Combine Scores ---
    if model_used: final_score = (0.3 * rule_score) + (0.7 * model_score) # Weight model higher
    else: final_score = rule_score # Fallback to rules only

    # --- Factor in IP Reputation (NEW) ---
    if ip_rep_result and ip_rep_result.get("is_malicious"):
        logger.info(f"Adjusting score for malicious IP reputation for {metadata.ip}")
        final_score += IP_REPUTATION_MALICIOUS_SCORE_BONUS
        increment_metric("score_adjusted_ip_reputation")

    # --- Placeholder for Unsupervised Learning ---
    # anomaly_score = get_anomaly_score(features_dict) # Hypothetical function
    # final_score = (final_score + anomaly_score) / 2 # Example blending

    final_score = max(0.0, min(1.0, final_score)) # Ensure score stays within bounds
    return final_score


async def classify_with_local_llm_api(metadata: RequestMetadata) -> bool | None:
    """ Classifies using configured local LLM API. """
    # (Implementation remains the same as previous version)
    if not LOCAL_LLM_API_URL or not LOCAL_LLM_MODEL: return None
    increment_metric("local_llm_checks_run")
    logger.info(f"Attempting classification for IP {metadata.ip} using local LLM API ({LOCAL_LLM_MODEL})...")
    prompt = f"""Analyze the following request metadata to classify the origin as MALICIOUS_BOT, BENIGN_CRAWLER, or HUMAN. Focus on detecting automated threats, not just any automation.

    **Request Details:**
    * **IP Address:** {metadata.ip}
    * **User-Agent:** {metadata.user_agent or 'N/A'}
    * **Requested Path:** {metadata.path or 'N/A'}
    * **Referer:** {metadata.referer or 'N/A'}
    * **Timestamp:** {metadata.timestamp}
    * **Selected Headers:** {json.dumps({k: v for k, v in (metadata.headers or {}).items() if k.lower() in ['accept', 'accept-language', 'connection', 'host', 'sec-ch-ua', 'sec-fetch-site', 'sec-fetch-mode', 'sec-fetch-user', 'sec-fetch-dest']})}

    **Instructions:** Respond ONLY with 'MALICIOUS_BOT', 'BENIGN_CRAWLER', or 'HUMAN'.
    """
    api_payload = { "model": LOCAL_LLM_MODEL, "messages": [{"role": "system", "content": "You are a security analysis assistant specializing in bot detection. Respond ONLY with 'MALICIOUS_BOT', 'BENIGN_CRAWLER', or 'HUMAN'."},{"role": "user", "content": prompt}], "temperature": 0.1, "stream": False }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LOCAL_LLM_API_URL, json=api_payload, timeout=LOCAL_LLM_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
            logger.info(f"Local LLM API response for {metadata.ip}: '{content}'")
            if "MALICIOUS_BOT" in content: return True
            elif "HUMAN" in content or "BENIGN_CRAWLER" in content: return False
            else: logger.warning(f"Unexpected classification from local LLM ({metadata.ip}): '{content}'"); increment_metric("local_llm_errors_unexpected_response"); return None
    except httpx.TimeoutException: logger.error(f"Timeout calling local LLM API ({LOCAL_LLM_API_URL}) for IP {metadata.ip} after {LOCAL_LLM_TIMEOUT}s"); increment_metric("local_llm_errors_timeout"); return None
    except httpx.RequestError as exc: logger.error(f"Request error calling local LLM API ({LOCAL_LLM_API_URL}) for IP {metadata.ip}: {exc}"); increment_metric("local_llm_errors_request"); return None
    except json.JSONDecodeError as exc: logger.error(f"JSON decode error processing LLM response for IP {metadata.ip}: {exc} - Response: {response.text[:500]}"); increment_metric("local_llm_errors_response_decode"); return None
    except Exception as e: logger.error(f"Unexpected error processing local LLM API response for IP {metadata.ip}: {e}", exc_info=True); increment_metric("local_llm_errors_unexpected"); return None


async def classify_with_external_api(metadata: RequestMetadata) -> bool | None:
    """ Classifies using configured external API. """
    # (Implementation remains the same as previous version)
    if not EXTERNAL_API_URL: return None
    increment_metric("external_api_checks_run")
    logger.info(f"Attempting classification for IP {metadata.ip} using External API...")
    external_payload = {"ipAddress": metadata.ip, "userAgent": metadata.user_agent, "referer": metadata.referer, "requestPath": metadata.path, "headers": metadata.headers}
    headers = { 'Content-Type': 'application/json' }
    if EXTERNAL_API_KEY: headers['Authorization'] = f"Bearer {EXTERNAL_API_KEY}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(EXTERNAL_API_URL, headers=headers, json=external_payload, timeout=EXTERNAL_API_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            is_bot = result.get("is_bot", None) # Needs to be adapted!
            logger.info(f"External API response for {metadata.ip}: IsBot={is_bot}")
            if isinstance(is_bot, bool): increment_metric("external_api_success"); return is_bot
            else: logger.warning(f"Unexpected response format from external API for {metadata.ip}. Response: {result}"); increment_metric("external_api_errors_unexpected_response"); return None
    except httpx.TimeoutException: logger.error(f"Timeout calling external API ({EXTERNAL_API_URL}) for IP {metadata.ip}"); increment_metric("external_api_errors_timeout"); return None
    except httpx.RequestError as exc: logger.error(f"Request error calling external API ({EXTERNAL_API_URL}) for IP {metadata.ip}: {exc}"); increment_metric("external_api_errors_request"); return None
    except json.JSONDecodeError as exc: logger.error(f"JSON decode error processing external API response for IP {metadata.ip}: {exc} - Response: {response.text[:500]}"); increment_metric("external_api_errors_response_decode"); return None
    except Exception as e: logger.error(f"Unexpected error processing external API response for IP {metadata.ip}: {e}", exc_info=True); increment_metric("external_api_errors_unexpected"); return None


# --- Webhook Forwarding ---
async def forward_to_webhook(payload: Dict[str, Any], reason: str):
    """Sends data to the configured webhook URL."""
    # (Implementation remains the same as previous version)
    if not WEBHOOK_URL: return
    increment_metric("webhooks_sent")
    serializable_payload = {}
    try: serializable_payload = json.loads(json.dumps(payload, default=str))
    except Exception as e: logger.error(f"Failed to serialize payload for webhook (IP: {payload.get('ip')}): {e}"); serializable_payload = {"ip": payload.get("ip", "unknown"), "error": "Payload serialization failed"}
    webhook_payload = { "event_type": "suspicious_activity_detected", "reason": reason, "timestamp_utc": datetime.datetime.utcnow().isoformat()+"Z", "details": serializable_payload }
    headers = {'Content-Type': 'application/json'}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(WEBHOOK_URL, headers=headers, json=webhook_payload, timeout=10.0)
            response.raise_for_status()
            logger.info(f"Webhook forwarded successfully for IP {payload.get('ip')}")
    except httpx.RequestError as exc: logger.error(f"Error forwarding to webhook {WEBHOOK_URL} for IP {payload.get('ip')}: {exc}"); increment_metric("webhook_errors_request")
    except Exception as e: logger.error(f"Unexpected error during webhook forwarding for IP {payload.get('ip')}: {e}", exc_info=True); increment_metric("webhook_errors_unexpected")


# --- CAPTCHA Trigger Placeholder (NEW) ---
async def trigger_captcha_challenge(metadata: RequestMetadata) -> bool:
    """Placeholder function for triggering a CAPTCHA challenge."""
    # In a real implementation, this might:
    # 1. Log the attempt.
    # 2. Set a short-lived flag in Redis for the IP/session.
    # 3. Return a specific status or payload that the caller (or Nginx via Lua) can use
    #    to redirect the user to the CAPTCHA_VERIFICATION_URL.
    # 4. The application at CAPTCHA_VERIFICATION_URL would handle showing and verifying the CAPTCHA,
    #    then potentially clearing the flag or notifying this service upon success.
    logger.info(f"CAPTCHA Triggered (Placeholder) for IP {metadata.ip}. Score between {CAPTCHA_SCORE_THRESHOLD_LOW} and {CAPTCHA_SCORE_THRESHOLD_HIGH}. Would redirect to {CAPTCHA_VERIFICATION_URL}")
    increment_metric("captcha_challenges_triggered")
    # For now, just return True indicating the trigger happened.
    return True


# --- API Endpoint (/escalate) ---
@app.post("/escalate")
async def handle_escalation(metadata_req: RequestMetadata, request: Request):
    """Receives request metadata, performs analysis, and triggers actions."""
    client_ip = request.client.host if request.client else "unknown"; increment_metric("escalation_requests_received");
    ip_under_test = metadata_req.ip
    action_taken = "analysis_complete"; is_bot_decision = None; final_score = -1.0 # Default score

    try:
        # --- Step 1: IP Reputation Check (Optional) ---
        ip_rep_result = None
        if ENABLE_IP_REPUTATION:
            ip_rep_result = await check_ip_reputation(ip_under_test)
            # Optional: Immediately escalate if reputation is definitively malicious?
            # if ip_rep_result and ip_rep_result.get("is_malicious"):
            #     logger.info(f"IP {ip_under_test} flagged by IP Reputation. Escalating.")
            #     is_bot_decision = True; action_taken = "webhook_triggered_ip_reputation"; increment_metric("bots_detected_ip_reputation");
            #     await forward_to_webhook(metadata_req.model_dump(mode='json'), f"IP Reputation Malicious (Score: {ip_rep_result.get('score', 'N/A')})")
            #     # Skip further checks if we block based on reputation alone
            #     # (Return statement moved to after final logging)

        # --- Step 2: Heuristic and Model Analysis ---
        # Only proceed if not already flagged by IP reputation (if that logic is added above)
        if is_bot_decision is None:
            final_score = run_heuristic_and_model_analysis(metadata_req, ip_rep_result)

            # --- Step 3: Decision Logic ---
            if final_score >= HEURISTIC_THRESHOLD_HIGH:
                is_bot_decision = True; action_taken = "webhook_triggered_high_score"; increment_metric("bots_detected_high_score");
                await forward_to_webhook(metadata_req.model_dump(mode='json'), f"High Combined Score ({final_score:.3f})")

            elif final_score < CAPTCHA_SCORE_THRESHOLD_LOW: # Clearly low score
                 is_bot_decision = False; action_taken = "classified_human_low_score"; increment_metric("humans_detected_low_score")

            elif ENABLE_CAPTCHA_TRIGGER and CAPTCHA_SCORE_THRESHOLD_LOW <= final_score < CAPTCHA_SCORE_THRESHOLD_HIGH:
                 # --- Step 3a: CAPTCHA Trigger (Borderline Score) ---
                 logger.info(f"IP {ip_under_test} has borderline score ({final_score:.3f}). Checking CAPTCHA trigger.")
                 captcha_needed = await trigger_captcha_challenge(metadata_req)
                 # Currently, this just logs. A real system needs a mechanism
                 # for the client/Nginx to receive this outcome and act.
                 # We'll set the action but won't block/allow yet.
                 action_taken = "captcha_triggered"
                 is_bot_decision = None # Remain uncertain until CAPTCHA result (if implemented)

            else: # Score is medium/high but below threshold, or CAPTCHA disabled/failed
                 # --- Step 3b: Deeper Analysis (LLM / External API) ---
                 logger.info(f"IP {ip_under_test} requires deeper check (Score: {final_score:.3f}).")
                 local_llm_result = await classify_with_local_llm_api(metadata_req)
                 if local_llm_result is True:
                     is_bot_decision = True; action_taken = "webhook_triggered_local_llm"; increment_metric("bots_detected_local_llm");
                     await forward_to_webhook(metadata_req.model_dump(mode='json'), "Local LLM Classification")
                 elif local_llm_result is False:
                     is_bot_decision = False; action_taken = "classified_human_local_llm"; increment_metric("humans_detected_local_llm")
                 else: # LLM failed or inconclusive
                     action_taken = "local_llm_inconclusive"
                     if EXTERNAL_API_URL: # Optional External API fallback
                         external_api_result = await classify_with_external_api(metadata_req)
                         if external_api_result is True:
                             is_bot_decision = True; action_taken = "webhook_triggered_external_api"; increment_metric("bots_detected_external_api");
                             await forward_to_webhook(metadata_req.model_dump(mode='json'), "External API Classification")
                         elif external_api_result is False:
                             is_bot_decision = False; action_taken = "classified_human_external_api"; increment_metric("humans_detected_external_api")
                         else: action_taken = "external_api_inconclusive"
                     # If no external API, decision remains None (uncertain)

    except ValidationError as e:
        logger.error(f"Invalid request payload received from {client_ip}: {e}")
        raise HTTPException(status_code=422, detail=f"Invalid payload: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during escalation processing for IP {ip_under_test}: {e}", exc_info=True)
        action_taken = "internal_server_error"
        is_bot_decision = None
        final_score = -1.0 # Indicate error state
        # Return 500 status code in the response directly
        return Response(status_code=500, content=json.dumps({"status": "error", "detail": "Internal server error"}), media_type="application/json")


    # --- Final Logging & Response ---
    log_msg = f"IP={ip_under_test}, Source={metadata_req.source}, Score={final_score:.3f}, Decision={is_bot_decision}, Action={action_taken}"
    if ip_rep_result: log_msg += f", IPRepMalicious={ip_rep_result.get('is_malicious')}, IPRepScore={ip_rep_result.get('score')}"
    logger.info(f"Escalation Complete: {log_msg}")

    # Return standard response
    return {"status": "processed", "action": action_taken, "is_bot_decision": is_bot_decision, "score": round(final_score, 3)}


# --- Metrics Endpoint ---
@app.get("/metrics")
async def get_metrics_endpoint():
    if not METRICS_AVAILABLE: raise HTTPException(status_code=501, detail="Metrics module not available")
    try:
        return get_metrics()
    except Exception as e:
        logger.error(f"Error retrieving metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")

# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """ Basic health check endpoint """
    redis_ok = False
    if redis_client_freq:
        try: redis_ok = redis_client_freq.ping()
        except Exception: redis_ok = False
    # Add checks for model loading, etc. if needed
    return {"status": "ok", "redis_frequency_connected": redis_ok, "model_loaded": MODEL_LOADED}


# --- Main ---
if __name__ == "__main__":
    import uvicorn
    logger.info("--- Escalation Engine Starting ---")
    if MODEL_LOADED: logger.info(f"Loaded RF Model from: {RF_MODEL_PATH}")
    else: logger.warning(f"RF Model NOT loaded from {RF_MODEL_PATH}. Using rule-based heuristics only.")
    if FREQUENCY_TRACKING_ENABLED: logger.info(f"Redis Frequency Tracking Enabled (DB: {REDIS_DB_FREQUENCY})")
    else: logger.warning(f"Redis Frequency Tracking DISABLED.")
    if not disallowed_paths: logger.warning(f"No robots.txt rules loaded from {ROBOTS_TXT_PATH}.")
    logger.info(f"Local LLM API configured: {'Yes (' + LOCAL_LLM_API_URL + ')' if LOCAL_LLM_API_URL else 'No'}")
    logger.info(f"External Classification API configured: {'Yes' if EXTERNAL_API_URL else 'No'}")
    logger.info(f"IP Reputation Check Enabled: {ENABLE_IP_REPUTATION} ({'URL Set' if IP_REPUTATION_API_URL else 'URL Not Set'})")
    logger.info(f"CAPTCHA Trigger Enabled: {ENABLE_CAPTCHA_TRIGGER} (Low: {CAPTCHA_SCORE_THRESHOLD_LOW}, High: {CAPTCHA_SCORE_THRESHOLD_HIGH})")
    logger.info(f"Webhook URL configured: {'Yes (' + WEBHOOK_URL + ')' if WEBHOOK_URL else 'No'}")
    logger.info("---------------------------------")
    uvicorn.run("escalation_engine:app", host="0.0.0.0", port=8003, workers=2, reload=False) # Use reload=True only for dev

    # Note: In production, consider using a WSGI server like Gunicorn with Uvicorn workers for better performance.
    # Example: gunicorn -k uvicorn.workers.UvicornWorker escalation_engine:app --bind
    