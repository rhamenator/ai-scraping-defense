# escalation/escalation_engine.py
from fastapi import FastAPI, Request, HTTPException, Response 
from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Any, Optional, Union
import httpx
import os
import datetime
import time
import json
import numpy as np
from urllib.parse import urlparse
import re
import asyncio
import logging
import sys
import ipaddress
import hashlib

# --- Refactored Imports ---
from src.shared.model_provider import get_model_adapter
from src.shared.decision_db import record_decision
from src.shared.redis_client import get_redis_connection
from src.shared.config import CONFIG

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from frequency_rs import get_realtime_frequency_features as rs_get_freq
    FREQUENCY_RS_AVAILABLE = True
    logger.info("frequency_rs module loaded successfully.")
except Exception as e:
    FREQUENCY_RS_AVAILABLE = False
    logger.warning(f"Could not import frequency_rs: {e}. Using Python fallback.")

# --- Metrics Import (Preserved from your original file) ---
try:
    from src.shared.metrics import (
        increment_counter_metric, get_metrics, 
        REDIS_ERRORS_FREQUENCY, IP_REPUTATION_CHECKS_RUN, IP_REPUTATION_SUCCESS,
        IP_REPUTATION_MALICIOUS, IP_REPUTATION_ERRORS_TIMEOUT, IP_REPUTATION_ERRORS_REQUEST,
        IP_REPUTATION_ERRORS_RESPONSE_DECODE, IP_REPUTATION_ERRORS_UNEXPECTED,
        HEURISTIC_CHECKS_RUN, FREQUENCY_ANALYSES_PERFORMED, RF_MODEL_PREDICTIONS,
        RF_MODEL_ERRORS, SCORE_ADJUSTED_IP_REPUTATION, LOCAL_LLM_CHECKS_RUN,
        LOCAL_LLM_ERRORS_UNEXPECTED_RESPONSE, LOCAL_LLM_ERRORS_TIMEOUT,
        LOCAL_LLM_ERRORS_REQUEST, LOCAL_LLM_ERRORS_RESPONSE_DECODE,
        LOCAL_LLM_ERRORS_UNEXPECTED, EXTERNAL_API_CHECKS_RUN, EXTERNAL_API_SUCCESS,
        EXTERNAL_API_ERRORS_UNEXPECTED_RESPONSE, EXTERNAL_API_ERRORS_TIMEOUT,
        EXTERNAL_API_ERRORS_REQUEST, EXTERNAL_API_ERRORS_RESPONSE_DECODE,
        EXTERNAL_API_ERRORS_UNEXPECTED, ESCALATION_WEBHOOKS_SENT,
        ESCALATION_WEBHOOK_ERRORS_REQUEST, ESCALATION_WEBHOOK_ERRORS_UNEXPECTED,
        CAPTCHA_CHALLENGES_TRIGGERED, ESCALATION_REQUESTS_RECEIVED,
        BOTS_DETECTED_IP_REPUTATION, BOTS_DETECTED_HIGH_SCORE,
        HUMANS_DETECTED_LOW_SCORE, BOTS_DETECTED_LOCAL_LLM,
        HUMANS_DETECTED_LOCAL_LLM, BOTS_DETECTED_EXTERNAL_API,
        HUMANS_DETECTED_EXTERNAL_API
    )
    METRICS_SYSTEM_AVAILABLE = True
    logger.info("Metrics system (prometheus client style) imported successfully by Escalation Engine.")
except ImportError:
    logger.warning("Could not import specific metrics or helpers from metrics.py. Metric incrementation will be no-op.")
    def increment_counter_metric(metric_instance, labels=None): pass
    def get_metrics() -> bytes: return b"# Metrics unavailable\n"
    class DummyCounter:
        def inc(self, amount=1): pass
    # Define all required metric objects as dummies
    REDIS_ERRORS_FREQUENCY = DummyCounter()
    IP_REPUTATION_CHECKS_RUN = DummyCounter(); IP_REPUTATION_SUCCESS = DummyCounter()
    IP_REPUTATION_MALICIOUS = DummyCounter(); IP_REPUTATION_ERRORS_TIMEOUT = DummyCounter()
    IP_REPUTATION_ERRORS_REQUEST = DummyCounter(); IP_REPUTATION_ERRORS_RESPONSE_DECODE = DummyCounter()
    IP_REPUTATION_ERRORS_UNEXPECTED = DummyCounter(); HEURISTIC_CHECKS_RUN = DummyCounter()
    FREQUENCY_ANALYSES_PERFORMED = DummyCounter(); RF_MODEL_PREDICTIONS = DummyCounter()
    RF_MODEL_ERRORS = DummyCounter(); SCORE_ADJUSTED_IP_REPUTATION = DummyCounter()
    LOCAL_LLM_CHECKS_RUN = DummyCounter(); LOCAL_LLM_ERRORS_UNEXPECTED_RESPONSE = DummyCounter()
    LOCAL_LLM_ERRORS_TIMEOUT = DummyCounter(); LOCAL_LLM_ERRORS_REQUEST = DummyCounter()
    LOCAL_LLM_ERRORS_RESPONSE_DECODE = DummyCounter(); LOCAL_LLM_ERRORS_UNEXPECTED = DummyCounter()
    EXTERNAL_API_CHECKS_RUN = DummyCounter(); EXTERNAL_API_SUCCESS = DummyCounter()
    EXTERNAL_API_ERRORS_UNEXPECTED_RESPONSE = DummyCounter(); EXTERNAL_API_ERRORS_TIMEOUT = DummyCounter()
    EXTERNAL_API_ERRORS_REQUEST = DummyCounter(); EXTERNAL_API_ERRORS_RESPONSE_DECODE = DummyCounter()
    EXTERNAL_API_ERRORS_UNEXPECTED = DummyCounter(); ESCALATION_WEBHOOKS_SENT = DummyCounter()
    ESCALATION_WEBHOOK_ERRORS_REQUEST = DummyCounter(); ESCALATION_WEBHOOK_ERRORS_UNEXPECTED = DummyCounter()
    CAPTCHA_CHALLENGES_TRIGGERED = DummyCounter(); ESCALATION_REQUESTS_RECEIVED = DummyCounter()
    BOTS_DETECTED_IP_REPUTATION = DummyCounter(); BOTS_DETECTED_HIGH_SCORE = DummyCounter()
    HUMANS_DETECTED_LOW_SCORE = DummyCounter(); BOTS_DETECTED_LOCAL_LLM = DummyCounter()
    HUMANS_DETECTED_LOCAL_LLM = DummyCounter(); BOTS_DETECTED_EXTERNAL_API = DummyCounter()
    HUMANS_DETECTED_EXTERNAL_API = DummyCounter()
    METRICS_SYSTEM_AVAILABLE = False

# --- Configuration (Preserved) ---
ESCALATION_THRESHOLD = CONFIG.ESCALATION_THRESHOLD
LOG_LEVEL = CONFIG.LOG_LEVEL
ESCALATION_API_KEY = CONFIG.ESCALATION_API_KEY

try:
    from user_agents import parse as ua_parse; UA_PARSER_AVAILABLE = True
except ImportError:
    ua_parse = None; UA_PARSER_AVAILABLE = False
    logger.warning("user-agents library not found. Detailed UA parsing disabled.")

WEBHOOK_URL = CONFIG.ESCALATION_WEBHOOK_URL
LOCAL_LLM_API_URL = CONFIG.LOCAL_LLM_API_URL
LOCAL_LLM_MODEL = CONFIG.LOCAL_LLM_MODEL
LOCAL_LLM_TIMEOUT = CONFIG.LOCAL_LLM_TIMEOUT
EXTERNAL_API_URL = CONFIG.EXTERNAL_API_URL
EXTERNAL_API_TIMEOUT = CONFIG.EXTERNAL_API_TIMEOUT
ENABLE_LOCAL_LLM_CLASSIFICATION = CONFIG.ENABLE_LOCAL_LLM_CLASSIFICATION
ENABLE_EXTERNAL_API_CLASSIFICATION = CONFIG.ENABLE_EXTERNAL_API_CLASSIFICATION

ENABLE_IP_REPUTATION = CONFIG.ENABLE_IP_REPUTATION
IP_REPUTATION_API_URL = CONFIG.IP_REPUTATION_API_URL
IP_REPUTATION_TIMEOUT = CONFIG.IP_REPUTATION_TIMEOUT
IP_REPUTATION_MALICIOUS_SCORE_BONUS = CONFIG.IP_REPUTATION_MALICIOUS_SCORE_BONUS
IP_REPUTATION_MIN_MALICIOUS_THRESHOLD = CONFIG.IP_REPUTATION_MIN_MALICIOUS_THRESHOLD

ENABLE_CAPTCHA_TRIGGER = CONFIG.ENABLE_CAPTCHA_TRIGGER
CAPTCHA_SCORE_THRESHOLD_LOW = CONFIG.CAPTCHA_SCORE_THRESHOLD_LOW
CAPTCHA_SCORE_THRESHOLD_HIGH = CONFIG.CAPTCHA_SCORE_THRESHOLD_HIGH
CAPTCHA_VERIFICATION_URL = CONFIG.CAPTCHA_VERIFICATION_URL
CAPTCHA_SECRET = CONFIG.CAPTCHA_SECRET
CAPTCHA_SUCCESS_LOG = CONFIG.CAPTCHA_SUCCESS_LOG

ROBOTS_TXT_PATH = CONFIG.TRAINING_ROBOTS_TXT_PATH

REDIS_DB_FREQUENCY = CONFIG.REDIS_DB_FREQUENCY
FREQUENCY_WINDOW_SECONDS = CONFIG.FREQUENCY_WINDOW_SECONDS
FREQUENCY_KEY_PREFIX = "freq:"
FREQUENCY_TRACKING_TTL = FREQUENCY_WINDOW_SECONDS + 60

# Browser fingerprint tracking configuration
REDIS_DB_FINGERPRINTS = CONFIG.REDIS_DB_FINGERPRINTS
FINGERPRINT_WINDOW_SECONDS = CONFIG.FINGERPRINT_WINDOW_SECONDS
FINGERPRINT_REUSE_THRESHOLD = CONFIG.FINGERPRINT_REUSE_THRESHOLD

HEURISTIC_THRESHOLD_LOW = 0.3
HEURISTIC_THRESHOLD_MEDIUM = 0.6
HEURISTIC_THRESHOLD_HIGH = 0.8

KNOWN_BAD_UAS_ENV = CONFIG.KNOWN_BAD_UAS
KNOWN_BAD_UAS = [ua.strip() for ua in KNOWN_BAD_UAS_ENV.split(',') if ua.strip()]
KNOWN_BENIGN_CRAWLERS_UAS_ENV = CONFIG.KNOWN_BENIGN_CRAWLERS_UAS
KNOWN_BENIGN_CRAWLERS_UAS = [ua.strip() for ua in KNOWN_BENIGN_CRAWLERS_UAS_ENV.split(',') if ua.strip()]


# --- Load Secrets ---
EXTERNAL_API_KEY = CONFIG.EXTERNAL_API_KEY
IP_REPUTATION_API_KEY = CONFIG.IP_REPUTATION_API_KEY

# --- Setup Clients & Load Resources ---
# The manual joblib loading and redis pool have been replaced by these abstractions.
model_adapter = None
MODEL_LOADED = False
try:
    model_adapter = get_model_adapter()
    if model_adapter and model_adapter.model:
        MODEL_LOADED = True
        logger.info(f"Model adapter '{os.getenv('MODEL_TYPE')}' loaded successfully.")
    else:
        logger.warning("Model adapter failed to initialize or load model. Heuristic scoring only.")
except Exception as e:
    logger.error(f"CRITICAL: Unhandled exception during model loading: {e}", exc_info=True)

redis_client_freq = get_redis_connection(db_number=REDIS_DB_FREQUENCY)
FREQUENCY_TRACKING_ENABLED = bool(redis_client_freq)

redis_client_fingerprints = get_redis_connection(db_number=REDIS_DB_FINGERPRINTS)
FINGERPRINT_TRACKING_ENABLED = bool(redis_client_fingerprints)

# Robots.txt loading (Preserved)
disallowed_paths = set()
def load_robots_txt(path):
    global disallowed_paths; disallowed_paths = set()
    try:
        current_ua_is_star = False 
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip().lower()
                if not line or line.startswith('#'): continue
                if line.startswith('user-agent:'):
                    ua_spec = line.split(':', 1)[1].strip()
                    current_ua_is_star = (ua_spec == '*')
                elif line.startswith('disallow:') and current_ua_is_star:
                    rule = line.split(':', 1)[1].strip()
                    if rule and rule != "/": disallowed_paths.add(rule)
    except FileNotFoundError: logger.warning(f"robots.txt not found at {path}.")
    except Exception as e: logger.error(f"Error loading robots.txt from {path}: {e}")

def is_path_disallowed(path):
    if not path or not disallowed_paths: return False
    try:
        for disallowed in disallowed_paths:
            if disallowed and path.startswith(disallowed): return True 
    except Exception: pass
    return False

load_robots_txt(ROBOTS_TXT_PATH) 

# --- Feature Extraction Logic (Preserved) ---
def extract_features(log_entry_dict: Dict[str, Any], freq_features: Dict[str, Any]) -> Dict[str, Any]:
    features: Dict[str, Any] = {}
    if not isinstance(log_entry_dict, dict): return features
    ua_string = log_entry_dict.get('user_agent', '') or ''
    referer = log_entry_dict.get('referer', '') or ''
    path = log_entry_dict.get('path', '') or ''
    
    features['ua_length'] = len(ua_string) 
    features['status_code'] = log_entry_dict.get('status', 0)
    features['bytes_sent'] = log_entry_dict.get('bytes', 0)
    features['http_method'] = log_entry_dict.get('method', 'UNKNOWN')
    features['path_depth'] = path.count('/')
    features['path_length'] = len(path)
    features['path_is_root'] = 1 if path == '/' else 0
    features['path_has_docs'] = 1 if '/docs' in path else 0
    features['path_is_wp'] = 1 if ('/wp-' in path or '/xmlrpc.php' in path) else 0
    features['path_disallowed'] = 1 if is_path_disallowed(path) else 0
    
    ua_lower = ua_string.lower()
    features['ua_is_known_bad'] = 1 if any(bad in ua_lower for bad in KNOWN_BAD_UAS) else 0
    features['ua_is_known_benign_crawler'] = 1 if any(good in ua_lower for good in KNOWN_BENIGN_CRAWLERS_UAS) else 0
    features['ua_is_empty'] = 1 if not ua_string else 0
    
    ua_parse_failed = False
    if UA_PARSER_AVAILABLE and ua_parse is not None and ua_string:
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
        except Exception: ua_parse_failed = True
    
    if not UA_PARSER_AVAILABLE or ua_parse_failed: 
        features['ua_browser_family'] = 'Unknown'; features['ua_os_family'] = 'Unknown'
        features['ua_device_family'] = 'Unknown'; features['ua_is_mobile'] = 0
        features['ua_is_tablet'] = 0; features['ua_is_pc'] = 0; features['ua_is_touch'] = 0
        features['ua_library_is_bot'] = features['ua_is_known_bad']
        
    features['referer_is_empty'] = 1 if not referer else 0
    features['referer_has_domain'] = 0
    try:
        if referer: parsed_referer = urlparse(referer); features['referer_has_domain'] = 1 if parsed_referer.netloc else 0
    except Exception: pass
    
    timestamp_val = log_entry_dict.get('timestamp')
    hour, dow = -1, -1
    if timestamp_val:
        try: 
            if isinstance(timestamp_val, str): ts = datetime.datetime.fromisoformat(timestamp_val.replace('Z', '+00:00'))
            elif isinstance(timestamp_val, datetime.datetime): ts = timestamp_val
            else: ts = None
            
            if ts: hour = ts.hour; dow = ts.weekday()
        except Exception: pass
    features['hour_of_day'] = hour; features['day_of_week'] = dow
    
    features[f'req_freq_{FREQUENCY_WINDOW_SECONDS}s'] = freq_features.get('count', 0)
    features['time_since_last_sec'] = freq_features.get('time_since', -1.0)
    if 'fingerprint_reuse_count' in log_entry_dict:
        features['fingerprint_reuse_count'] = log_entry_dict['fingerprint_reuse_count']
    return features

# --- Real-time Frequency Calculation ---
def _get_realtime_frequency_features_py(ip: str) -> dict:
    features = {'count': 0, 'time_since': -1.0}
    if not FREQUENCY_TRACKING_ENABLED or not ip or not redis_client_freq:
        return features
    try:
        now_unix = time.time(); window_start_unix = now_unix - FREQUENCY_WINDOW_SECONDS
        now_ms_str = f"{now_unix:.6f}"; redis_key = f"{FREQUENCY_KEY_PREFIX}{ip}"
        pipe = redis_client_freq.pipeline()
        pipe.zremrangebyscore(redis_key, '-inf', f'({window_start_unix}')
        pipe.zadd(redis_key, {now_ms_str: now_unix})
        pipe.zcount(redis_key, window_start_unix, now_unix)
        pipe.zrange(redis_key, -2, -1, withscores=True)
        pipe.expire(redis_key, FREQUENCY_TRACKING_TTL)
        results = pipe.execute()

        current_count = results[2] if len(results) > 2 and isinstance(results[2], int) else 0
        features['count'] = max(0, current_count - 1)

        recent_entries = results[3] if len(results) > 3 and isinstance(results[3], list) else []
        if len(recent_entries) > 1:
            last_ts_score = float(recent_entries[-2][1])
            time_diff = now_unix - last_ts_score
            features['time_since'] = round(time_diff, 3)
        elif len(recent_entries) == 1 and current_count == 1:
            features['time_since'] = -1.0
    except Exception as e:
        logger.warning(f"Redis error during frequency check for IP {ip}: {e}")
        increment_counter_metric(REDIS_ERRORS_FREQUENCY)
    return features

def get_realtime_frequency_features(ip: str) -> dict:
    if FREQUENCY_RS_AVAILABLE and FREQUENCY_TRACKING_ENABLED and ip:
        try:
            count, time_since = rs_get_freq(
                ip,
                REDIS_DB_FREQUENCY,
                FREQUENCY_WINDOW_SECONDS,
                FREQUENCY_KEY_PREFIX,
                FREQUENCY_TRACKING_TTL,
            )
            return {'count': int(count), 'time_since': float(time_since)}
        except Exception as e:
            logger.warning(f"frequency_rs error for IP {ip}: {e}; falling back to Python implementation")
            increment_counter_metric(REDIS_ERRORS_FREQUENCY)
    return _get_realtime_frequency_features_py(ip)

# --- Browser Fingerprint Tracking ---
def compute_browser_fingerprint(metadata: "RequestMetadata") -> str:
    ua = (metadata.user_agent or "").lower()
    headers = metadata.headers or {}
    parts = [
        ua,
        (headers.get('accept-language') or '').lower(),
        (headers.get('accept') or '').lower(),
        (headers.get('sec-ch-ua') or '').lower(),
        (headers.get('sec-fetch-site') or '').lower(),
    ]
    fp_raw = "|".join(parts)
    return hashlib.sha256(fp_raw.encode('utf-8')).hexdigest()

def track_fingerprint(fingerprint: str, ip: str) -> int:
    if not FINGERPRINT_TRACKING_ENABLED or not fingerprint or not redis_client_fingerprints:
        return 1
    try:
        key = f"fp:{fingerprint}"
        redis_client_fingerprints.sadd(key, ip)
        redis_client_fingerprints.expire(key, FINGERPRINT_WINDOW_SECONDS)
        return int(redis_client_fingerprints.scard(key))
    except Exception as e:
        logger.error(f"Redis error during fingerprint tracking for IP {ip}: {e}")
        return 1

# --- IP Reputation Check (Preserved) ---
async def check_ip_reputation(ip: str) -> Optional[Dict[str, Any]]:
    if not ENABLE_IP_REPUTATION or not IP_REPUTATION_API_URL or not ip: return None
    increment_counter_metric(IP_REPUTATION_CHECKS_RUN)
    logger.info(f"Checking IP reputation for {ip} using {IP_REPUTATION_API_URL}")
    headers = {'Accept': 'application/json'}
    params = {'ipAddress': ip}
    if IP_REPUTATION_API_KEY: headers['Authorization'] = f"Bearer {IP_REPUTATION_API_KEY}"
    response = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(IP_REPUTATION_API_URL, params=params, headers=headers, timeout=IP_REPUTATION_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            logger.debug(f"IP Reputation API response for {ip}: {result}")
            is_malicious = False; score_val = result.get("abuseConfidenceScore", 0) 
            score = float(score_val) if score_val is not None else 0.0
            if score >= IP_REPUTATION_MIN_MALICIOUS_THRESHOLD: is_malicious = True
            increment_counter_metric(IP_REPUTATION_SUCCESS)
            if is_malicious: increment_counter_metric(IP_REPUTATION_MALICIOUS)
            return {"is_malicious": is_malicious, "score": score, "raw_response": result}
    except httpx.TimeoutException: logger.error(f"Timeout checking IP reputation for {ip}"); increment_counter_metric(IP_REPUTATION_ERRORS_TIMEOUT); return None
    except httpx.RequestError as exc: logger.error(f"Request error checking IP reputation for {ip}: {exc}"); increment_counter_metric(IP_REPUTATION_ERRORS_REQUEST); return None
    except json.JSONDecodeError as exc: 
        resp_text = response.text[:500] if response is not None and hasattr(response, "text") else "<no response>"
        logger.error(f"JSON decode error IP rep for {ip}: {exc} - Resp: {resp_text}"); increment_counter_metric(IP_REPUTATION_ERRORS_RESPONSE_DECODE); return None
    except Exception as e: logger.error(f"Unexpected error IP rep for {ip}: {e}", exc_info=True); increment_counter_metric(IP_REPUTATION_ERRORS_UNEXPECTED); return None

# --- Pydantic Models (Preserved) ---
class RequestMetadata(BaseModel):
    timestamp: Union[str, datetime.datetime]
    ip: str
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    path: Optional[str] = None
    method: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    source: str

# --- FastAPI App ---
app = FastAPI(title="Escalation Engine", description="Analyzes suspicious requests and escalates if necessary.")

# --- Analysis & Classification Functions ---
def run_heuristic_and_model_analysis(metadata: RequestMetadata, ip_rep_result: Optional[Dict[str, Any]] = None) -> float:
    increment_counter_metric(HEURISTIC_CHECKS_RUN); rule_score = 0.0; model_score = 0.5; model_used = False; final_score = 0.5
    frequency_features = get_realtime_frequency_features(metadata.ip)
    increment_counter_metric(FREQUENCY_ANALYSES_PERFORMED)
    
    log_entry_dict = metadata.model_dump()
    if isinstance(log_entry_dict.get('timestamp'), datetime.datetime): 
        log_entry_dict['timestamp'] = log_entry_dict['timestamp'].isoformat()

    ua = (metadata.user_agent or "").lower()
    path = metadata.path or ''
    headers = metadata.headers or {}
    method = (metadata.method or headers.get('x-original-method') or headers.get('method') or 'GET').upper()

    fingerprint = compute_browser_fingerprint(metadata)
    fp_count = track_fingerprint(fingerprint, metadata.ip)
    log_entry_dict['fingerprint_reuse_count'] = fp_count
    if fp_count > FINGERPRINT_REUSE_THRESHOLD:
        rule_score += 0.2

    is_known_benign = any(good in ua for good in KNOWN_BENIGN_CRAWLERS_UAS)
    if any(bad in ua for bad in KNOWN_BAD_UAS) and not is_known_benign:
        rule_score += 0.7
    if not metadata.user_agent:
        rule_score += 0.5
    if is_path_disallowed(path) and not is_known_benign:
        rule_score += 0.6
    if method not in {"GET", "HEAD"}:
        rule_score += 0.2
    if 'accept-language' not in {k.lower() for k in headers.keys()}:
        rule_score += 0.1
    if frequency_features.get('count', 0) > 60:
        rule_score += 0.3
    elif frequency_features.get('count', 0) > 30:
        rule_score += 0.1
    if frequency_features.get('time_since', -1.0) != -1.0 and frequency_features.get('time_since', -1.0) < 0.3:
        rule_score += 0.2
    if is_known_benign:
        rule_score -= 0.5
    rule_score = max(0.0, min(1.0, rule_score))

    # --- THIS IS THE PRIMARY CHANGE ---
    # It now uses the model_adapter instead of the direct model_pipeline.
    if MODEL_LOADED and model_adapter:
        try:
            features_dict = extract_features(log_entry_dict, frequency_features)
            if features_dict:
                # The adapter's predict method is called here.
                probabilities = model_adapter.predict([features_dict])
                model_score = probabilities[0][1] 
                model_used = True
                increment_counter_metric(RF_MODEL_PREDICTIONS)
            else: 
                logger.warning(f"Could not extract features for RF model (IP: {metadata.ip})")
        except Exception as e: 
            logger.error(f"RF model prediction failed for IP {metadata.ip}: {e}", exc_info=True)
            increment_counter_metric(RF_MODEL_ERRORS)
    # --- END OF CHANGE ---
    
    if model_used: final_score = (0.3 * rule_score) + (0.7 * model_score)
    else: final_score = rule_score

    if ip_rep_result and ip_rep_result.get("is_malicious"):
        logger.info(f"Adjusting score for malicious IP reputation for {metadata.ip}")
        final_score += IP_REPUTATION_MALICIOUS_SCORE_BONUS
        increment_counter_metric(SCORE_ADJUSTED_IP_REPUTATION)
    
    final_score = max(0.0, min(1.0, final_score))
    return final_score

# --- All other helper functions are preserved as-is ---
async def classify_with_local_llm_api(metadata: RequestMetadata) -> Optional[bool]:
    if not LOCAL_LLM_API_URL or not LOCAL_LLM_MODEL: return None
    increment_counter_metric(LOCAL_LLM_CHECKS_RUN)
    logger.info(f"Attempting classification for IP {metadata.ip} using local LLM API ({LOCAL_LLM_MODEL})...")
    safe_metadata = metadata.model_dump()
    try:
        prompt_json = json.dumps(safe_metadata, ensure_ascii=False)
    except Exception:
        prompt_json = json.dumps({"ip": metadata.ip, "path": metadata.path})
    prompt = f"Analyze the following request JSON and classify as MALICIOUS_BOT, BENIGN_CRAWLER, or HUMAN: {prompt_json}"
    api_payload = {"model": LOCAL_LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "stream": False}
    response = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LOCAL_LLM_API_URL, json=api_payload, timeout=LOCAL_LLM_TIMEOUT)
            response.raise_for_status(); result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
            safe_content = content.replace("\n", " ")[:200]
            logger.info(f"Local LLM API response for {metadata.ip}: '{safe_content}'")
            if "MALICIOUS_BOT" in content: return True
            elif "HUMAN" in content or "BENIGN_CRAWLER" in content: return False
            else: logger.warning(f"Unexpected classification LLM ({metadata.ip}): '{content}'"); increment_counter_metric(LOCAL_LLM_ERRORS_UNEXPECTED_RESPONSE); return None
    except httpx.TimeoutException: logger.error(f"Timeout LLM API ({LOCAL_LLM_API_URL}) for IP {metadata.ip}"); increment_counter_metric(LOCAL_LLM_ERRORS_TIMEOUT); return None
    except httpx.RequestError as exc: logger.error(f"Request error LLM API ({LOCAL_LLM_API_URL}) for IP {metadata.ip}: {exc}"); increment_counter_metric(LOCAL_LLM_ERRORS_REQUEST); return None
    except json.JSONDecodeError as exc: 
        resp_text = response.text[:500] if response is not None and hasattr(response, "text") else "<no response>"
        logger.error(f"JSON decode error LLM for {metadata.ip}: {exc} - Resp: {resp_text}"); increment_counter_metric(LOCAL_LLM_ERRORS_RESPONSE_DECODE); return None
    except Exception as e: logger.error(f"Unexpected error LLM API for IP {metadata.ip}: {e}", exc_info=True); increment_counter_metric(LOCAL_LLM_ERRORS_UNEXPECTED); return None

async def classify_with_external_api(metadata: RequestMetadata) -> Optional[bool]:
    if not EXTERNAL_API_URL: return None
    increment_counter_metric(EXTERNAL_API_CHECKS_RUN)
    logger.info(f"Attempting classification for IP {metadata.ip} using External API...")
    headers_to_send = metadata.headers if metadata.headers is not None else {}
    external_payload = {"ipAddress": metadata.ip, "userAgent": metadata.user_agent, "referer": metadata.referer, "requestPath": metadata.path, "headers": headers_to_send}
    
    req_headers = { 'Content-Type': 'application/json' }
    if EXTERNAL_API_KEY: req_headers['Authorization'] = f"Bearer {EXTERNAL_API_KEY}"
    response = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(EXTERNAL_API_URL, headers=req_headers, json=external_payload, timeout=EXTERNAL_API_TIMEOUT)
            response.raise_for_status(); result = response.json()
            is_bot = result.get("is_bot", None) 
            logger.info(f"External API response for {metadata.ip}: IsBot={is_bot}")
            if isinstance(is_bot, bool): increment_counter_metric(EXTERNAL_API_SUCCESS); return is_bot
            else: logger.warning(f"Unexpected response external API for {metadata.ip}. Resp: {result}"); increment_counter_metric(EXTERNAL_API_ERRORS_UNEXPECTED_RESPONSE); return None
    except httpx.TimeoutException: logger.error(f"Timeout external API ({EXTERNAL_API_URL}) for IP {metadata.ip}"); increment_counter_metric(EXTERNAL_API_ERRORS_TIMEOUT); return None
    except httpx.RequestError as exc: logger.error(f"Request error external API ({EXTERNAL_API_URL}) for IP {metadata.ip}: {exc}"); increment_counter_metric(EXTERNAL_API_ERRORS_REQUEST); return None
    except json.JSONDecodeError as exc: 
        resp_text = response.text[:500] if response is not None and hasattr(response, "text") else "<no response>"
        logger.error(f"JSON decode error external API for {metadata.ip}: {exc} - Resp: {resp_text}"); increment_counter_metric(EXTERNAL_API_ERRORS_RESPONSE_DECODE); return None
    except Exception as e: logger.error(f"Unexpected error external API for IP {metadata.ip}: {e}", exc_info=True); increment_counter_metric(EXTERNAL_API_ERRORS_UNEXPECTED); return None

async def forward_to_webhook(payload: Dict[str, Any], reason: str):
    """Send a prepared webhook payload."""
    if not WEBHOOK_URL:
        return
    increment_counter_metric(ESCALATION_WEBHOOKS_SENT)
    headers = {"Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(WEBHOOK_URL, headers=headers, json=payload, timeout=10.0)
            resp.raise_for_status()
            ip_log = payload.get("details", {}).get("ip", payload.get("ip"))
            logger.info(f"Webhook forwarded successfully for IP {ip_log}")
    except httpx.RequestError as exc:
        logger.error(f"Error forwarding to webhook {WEBHOOK_URL} for IP {payload.get('ip')}: {exc}")
        increment_counter_metric(ESCALATION_WEBHOOK_ERRORS_REQUEST)
    except Exception as e:
        logger.error(f"Unexpected error during webhook forwarding for IP {payload.get('ip')}: {e}", exc_info=True)
        increment_counter_metric(ESCALATION_WEBHOOK_ERRORS_UNEXPECTED)

def build_webhook_payload(metadata: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Create a standard webhook payload from request metadata."""
    try:
        serializable = json.loads(json.dumps(metadata, default=str))
    except Exception as e:
        logger.error(f"Failed to serialize payload for webhook (IP: {metadata.get('ip')}): {e}")
        serializable = {"ip": metadata.get("ip", "unknown"), "error": "Payload serialization failed"}
    return {
        "event_type": "suspicious_activity_detected",
        "reason": reason,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "details": serializable,
    }

async def trigger_captcha_challenge(metadata: RequestMetadata) -> bool:
    """Verify a reCAPTCHA token if provided and log the outcome."""
    increment_counter_metric(CAPTCHA_CHALLENGES_TRIGGERED)
    token = None
    if metadata.headers:
        token = metadata.headers.get("x-captcha-token")
    if not token:
        logger.info(f"CAPTCHA challenge issued for IP {metadata.ip}; awaiting token")
        return False
    if not CAPTCHA_SECRET:
        logger.error("CAPTCHA secret not configured")
        return False
    verify_payload = {"secret": CAPTCHA_SECRET, "response": token, "remoteip": metadata.ip}
    url = CAPTCHA_VERIFICATION_URL or "https://www.google.com/recaptcha/api/siteverify"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=verify_payload, timeout=10.0)
            resp.raise_for_status()
            result = resp.json()
            success = bool(result.get("success"))
    except Exception as e:
        logger.error(f"Error verifying CAPTCHA for IP {metadata.ip}: {e}", exc_info=True)
        return False
    if success:
        try:
            os.makedirs(os.path.dirname(CAPTCHA_SUCCESS_LOG), exist_ok=True)
            with open(CAPTCHA_SUCCESS_LOG, "a") as f:
                f.write(
                    f"{datetime.datetime.now(datetime.timezone.utc).isoformat()},{metadata.ip}\n"
                )
        except Exception as e:
            logger.error(f"Failed to log CAPTCHA success: {e}")
        logger.info(f"CAPTCHA verified for IP {metadata.ip}")
    else:
        logger.info(f"CAPTCHA failed for IP {metadata.ip}")
    return success

# --- API Endpoint (/escalate) (Preserved) ---
@app.post("/escalate")
async def handle_escalation(metadata_req: RequestMetadata, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if ESCALATION_API_KEY and request.headers.get("X-API-Key") != ESCALATION_API_KEY:
        logger.warning(f"Unauthorized escalation attempt from {client_ip}")
        raise HTTPException(status_code=401, detail="Unauthorized")
    increment_counter_metric(ESCALATION_REQUESTS_RECEIVED)
    ip_under_test = metadata_req.ip
    try:
        ipaddress.ip_address(ip_under_test)
    except ValueError:
        logger.warning(f"Invalid IP provided to escalation endpoint: {ip_under_test}")
        raise HTTPException(status_code=400, detail="Invalid IP address")
    action_taken = "analysis_complete"; is_bot_decision: Optional[bool] = None; final_score = -1.0

    try:
        # Launch asynchronous checks concurrently
        tasks = []
        ip_rep_task = local_llm_task = external_api_task = None

        if ENABLE_IP_REPUTATION:
            ip_rep_task = asyncio.create_task(check_ip_reputation(ip_under_test))
            tasks.append(ip_rep_task)
        if ENABLE_LOCAL_LLM_CLASSIFICATION:
            local_llm_task = asyncio.create_task(classify_with_local_llm_api(metadata_req))
            tasks.append(local_llm_task)
        if ENABLE_EXTERNAL_API_CLASSIFICATION:
            external_api_task = asyncio.create_task(classify_with_external_api(metadata_req))
            tasks.append(external_api_task)

        # Calculate heuristic/model score while async tasks run
        base_score = run_heuristic_and_model_analysis(metadata_req, None)

        ip_rep_result = None
        local_llm_result = None
        external_api_result = None

        if tasks:
            max_timeout = max(
                IP_REPUTATION_TIMEOUT if ip_rep_task else 0,
                LOCAL_LLM_TIMEOUT if local_llm_task else 0,
                EXTERNAL_API_TIMEOUT if external_api_task else 0,
            ) + 1.0
            try:
                results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=max_timeout)
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for async checks for IP {ip_under_test}")
                for t in tasks:
                    t.cancel()
                results = [None] * len(tasks)

            idx = 0
            if ip_rep_task:
                res = results[idx]; idx += 1
                if isinstance(res, Exception):
                    logger.error(f"IP reputation task error for {ip_under_test}: {res}")
                else:
                    ip_rep_result = res
            if local_llm_task:
                res = results[idx]; idx += 1
                if isinstance(res, Exception):
                    logger.error(f"Local LLM task error for {ip_under_test}: {res}")
                else:
                    local_llm_result = res
            if external_api_task:
                res = results[idx]; idx += 1
                if isinstance(res, Exception):
                    logger.error(f"External API task error for {ip_under_test}: {res}")
                else:
                    external_api_result = res

        # Adjust score with IP reputation if malicious
        final_score = base_score
        if ip_rep_result and ip_rep_result.get("is_malicious"):
            logger.info(f"IP {ip_under_test} flagged by IP Reputation. Escalating directly.")
            increment_counter_metric(BOTS_DETECTED_IP_REPUTATION)
            increment_counter_metric(SCORE_ADJUSTED_IP_REPUTATION)
            action_taken = "webhook_triggered_ip_reputation"
            is_bot_decision = True
            final_score = min(1.0, max(0.0, final_score + IP_REPUTATION_MALICIOUS_SCORE_BONUS))
            payload = build_webhook_payload(
                metadata_req.model_dump(mode='json'),
                f"IP Reputation Malicious (Score: {ip_rep_result.get('score', 'N/A')})",
            )
            await forward_to_webhook(payload, "IP Reputation Malicious")

        if is_bot_decision is None:
            final_score = min(1.0, max(0.0, final_score))

            if final_score >= HEURISTIC_THRESHOLD_HIGH:
                is_bot_decision = True; action_taken = "webhook_triggered_high_score"
                increment_counter_metric(BOTS_DETECTED_HIGH_SCORE)
                payload = build_webhook_payload(
                    metadata_req.model_dump(mode='json'),
                    f"High Combined Score ({final_score:.3f})",
                )
                await forward_to_webhook(payload, "High Combined Score")
            elif final_score < CAPTCHA_SCORE_THRESHOLD_LOW:
                is_bot_decision = False; action_taken = "classified_human_low_score"
                increment_counter_metric(HUMANS_DETECTED_LOW_SCORE)
            elif ENABLE_CAPTCHA_TRIGGER and CAPTCHA_SCORE_THRESHOLD_LOW <= final_score < CAPTCHA_SCORE_THRESHOLD_HIGH:
                await trigger_captcha_challenge(metadata_req)
                action_taken = "captcha_triggered"; is_bot_decision = None
            else:
                logger.info(f"IP {ip_under_test} requires deeper check (Score: {final_score:.3f}).")
                if local_llm_result is True:
                    is_bot_decision = True; action_taken = "webhook_triggered_local_llm"
                    increment_counter_metric(BOTS_DETECTED_LOCAL_LLM)
                    payload = build_webhook_payload(
                        metadata_req.model_dump(mode='json'),
                        "Local LLM Classification",
                    )
                    await forward_to_webhook(payload, "Local LLM Classification")
                elif local_llm_result is False:
                    is_bot_decision = False; action_taken = "classified_human_local_llm"
                    increment_counter_metric(HUMANS_DETECTED_LOCAL_LLM)
                else:
                    action_taken = "local_llm_inconclusive"
                    if external_api_task is not None:
                        if external_api_result is True:
                            is_bot_decision = True; action_taken = "webhook_triggered_external_api"
                            increment_counter_metric(BOTS_DETECTED_EXTERNAL_API)
                            payload = build_webhook_payload(
                                metadata_req.model_dump(mode='json'),
                                "External API Classification",
                            )
                            await forward_to_webhook(payload, "External API Classification")
                        elif external_api_result is False:
                            is_bot_decision = False; action_taken = "classified_human_external_api"
                            increment_counter_metric(HUMANS_DETECTED_EXTERNAL_API)
                        else:
                            action_taken = "external_api_inconclusive"
    
    except ValidationError as e:
        logger.error(f"Invalid request payload received from {client_ip}: {e.errors()}") 
        raise HTTPException(status_code=422, detail=f"Invalid payload: {e.errors()}")
    except Exception as e:
        logger.error(f"Unexpected error during escalation for IP {ip_under_test}: {e}", exc_info=True)
        action_taken = "internal_server_error"; is_bot_decision = None; final_score = -1.0
        return Response(content=json.dumps({"status": "error", "detail": "Internal server error"}), 
                        status_code=500, media_type="application/json")


    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        record_decision(ip_under_test, metadata_req.source, final_score, is_bot_decision, action_taken, timestamp)
    except Exception as e:
        logger.error(f"Failed to record decision for IP {ip_under_test}: {e}", exc_info=True)

    log_msg = f"IP={ip_under_test}, Source={metadata_req.source}, Score={final_score:.3f}, Decision={is_bot_decision}, Action={action_taken}"
    if ip_rep_result:
        log_msg += f", IPRepMalicious={ip_rep_result.get('is_malicious')}, IPRepScore={ip_rep_result.get('score')}"
    logger.info(f"Escalation Complete: {log_msg}")
    return {"status": "processed", "action": action_taken, "is_bot_decision": is_bot_decision, "score": round(final_score, 3)}

# --- Metrics Endpoint (Preserved) ---
@app.get("/metrics")
async def get_metrics_endpoint_escalation(): 
    if not METRICS_SYSTEM_AVAILABLE: 
        return Response(content=b"# Metrics system unavailable in escalation_engine\n", media_type="text/plain; version=0.0.4")
    try:
        prometheus_metrics_bytes = get_metrics()
        return Response(content=prometheus_metrics_bytes, media_type="text/plain; version=0.0.4")
    except Exception as e:
        logger.error(f"Error retrieving metrics: {e}", exc_info=True)
        return Response(content=b"# Error retrieving metrics\n", media_type="text/plain; version=0.0.4", status_code=500)

# --- Health Check Endpoint (Preserved) ---
@app.get("/health")
async def health_check():
    redis_ok = False
    if redis_client_freq:
        try: redis_ok = redis_client_freq.ping()
        except Exception: redis_ok = False
    return {"status": "ok", "redis_frequency_connected": redis_ok, "model_loaded": MODEL_LOADED}

# --- Main (Preserved) ---
if __name__ == "__main__":
    import uvicorn
    port = CONFIG.ESCALATION_ENGINE_PORT
    workers = int(os.getenv("UVICORN_WORKERS", 2))
    log_level = CONFIG.LOG_LEVEL.lower()

    logger.info("--- Escalation Engine Starting ---")
    if MODEL_LOADED: logger.info(f"Loaded Model Adapter Type: {os.getenv('MODEL_TYPE')}")
    else: logger.warning(f"Model NOT loaded. Using rule-based heuristics only.")
    if FREQUENCY_TRACKING_ENABLED: logger.info(f"Redis Frequency Tracking Enabled (DB: {REDIS_DB_FREQUENCY})")
    else: logger.warning(f"Redis Frequency Tracking DISABLED.")
    if not disallowed_paths: logger.warning(f"No robots.txt rules loaded from {ROBOTS_TXT_PATH}.")
    logger.info(f"Local LLM API configured: {'Yes (' + str(LOCAL_LLM_API_URL) + ')' if LOCAL_LLM_API_URL else 'No'}")
    logger.info(f"External Classification API configured: {'Yes' if EXTERNAL_API_URL else 'No'}")
    logger.info(f"IP Reputation Check Enabled: {ENABLE_IP_REPUTATION} ({'URL Set' if IP_REPUTATION_API_URL else 'URL Not Set'})")
    logger.info(f"CAPTCHA Trigger Enabled: {ENABLE_CAPTCHA_TRIGGER} (Low: {CAPTCHA_SCORE_THRESHOLD_LOW}, High: {CAPTCHA_SCORE_THRESHOLD_HIGH})")
    logger.info(f"Webhook URL configured: {'Yes (' + str(WEBHOOK_URL) + ')' if WEBHOOK_URL else 'No'}")
    logger.info("---------------------------------")
    logger.info(f"Starting Escalation Engine on port {port}")
    uvicorn.run("src.escalation.escalation_engine:app", host="0.0.0.0", port=port, workers=workers, log_level=log_level, reload=False)