"""Multi-Factor Authentication utilities including backup codes and adaptive auth."""
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Optional

import bcrypt
from redis.exceptions import RedisError

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

# Configuration
BACKUP_CODE_LENGTH = 8
BACKUP_CODE_COUNT = 10
BACKUP_CODE_TTL = 90 * 24 * 3600  # 90 days
MFA_RECOVERY_WINDOW = 3600  # 1 hour for recovery attempts

# Risk scoring thresholds
RISK_THRESHOLD_LOW = 0.3
RISK_THRESHOLD_MEDIUM = 0.6
RISK_THRESHOLD_HIGH = 0.8


def _backup_codes_key(user: str) -> str:
    """Get Redis key for backup codes."""
    return tenant_key(f"mfa:backup_codes:{user}")


def _mfa_attempts_key(user: str) -> str:
    """Get Redis key for MFA attempt tracking."""
    return tenant_key(f"mfa:attempts:{user}")


def _risk_score_key(user: str, client_ip: str) -> str:
    """Get Redis key for risk score."""
    return tenant_key(f"mfa:risk:{user}:{client_ip}")


def _trusted_device_key(user: str, device_id: str) -> str:
    """Get Redis key for trusted devices."""
    return tenant_key(f"mfa:trusted:{user}:{device_id}")


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    """
    Generate cryptographically secure backup codes.
    
    Args:
        count: Number of backup codes to generate
        
    Returns:
        List of backup codes (plaintext)
    """
    codes = []
    for _ in range(count):
        # Generate random code with digits only for easier input
        code = "".join(str(secrets.randbelow(10)) for _ in range(BACKUP_CODE_LENGTH))
        codes.append(code)
    return codes


def hash_backup_code(code: str) -> str:
    """
    Hash a backup code using bcrypt for secure storage.
    
    Args:
        code: Plaintext backup code
        
    Returns:
        Bcrypt hash of the code
    """
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def store_backup_codes(user: str, codes: list[str]) -> bool:
    """
    Store hashed backup codes for a user.
    
    Args:
        user: Username
        codes: List of plaintext backup codes
        
    Returns:
        True if successful, False otherwise
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        logger.error("Redis unavailable, cannot store backup codes")
        return False
    
    try:
        # Hash all codes before storage
        hashed_codes = [hash_backup_code(code) for code in codes]
        data = {
            "codes": hashed_codes,
            "created_at": time.time(),
            "used": [False] * len(hashed_codes),
        }
        redis_conn.set(
            _backup_codes_key(user),
            json.dumps(data),
            ex=BACKUP_CODE_TTL,
        )
        logger.info(f"Stored {len(codes)} backup codes for user {user}")
        return True
    except RedisError as e:
        logger.error(f"Failed to store backup codes: {e}")
        return False


def verify_backup_code(user: str, code: str) -> bool:
    """
    Verify a backup code and mark it as used.
    
    Args:
        user: Username
        code: Plaintext backup code to verify
        
    Returns:
        True if code is valid and unused, False otherwise
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        logger.error("Redis unavailable, cannot verify backup code")
        return False
    
    try:
        key = _backup_codes_key(user)
        raw = redis_conn.get(key)
        if not raw:
            return False
        
        data = json.loads(raw)
        codes = data.get("codes", [])
        used = data.get("used", [False] * len(codes))
        
        # Check each unused code
        for i, hashed_code in enumerate(codes):
            if not used[i] and bcrypt.checkpw(code.encode(), hashed_code.encode()):
                # Mark as used
                used[i] = True
                data["used"] = used
                
                # Update Redis with remaining TTL
                ttl = redis_conn.ttl(key)
                if ttl > 0:
                    redis_conn.set(key, json.dumps(data), ex=ttl)
                else:
                    redis_conn.set(key, json.dumps(data), ex=BACKUP_CODE_TTL)
                
                logger.info(f"Backup code verified for user {user}")
                return True
        
        return False
    except (RedisError, json.JSONDecodeError) as e:
        logger.error(f"Failed to verify backup code: {e}")
        return False


def get_remaining_backup_codes_count(user: str) -> int:
    """
    Get the number of unused backup codes for a user.
    
    Args:
        user: Username
        
    Returns:
        Number of unused backup codes, or 0 if none or error
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        return 0
    
    try:
        raw = redis_conn.get(_backup_codes_key(user))
        if not raw:
            return 0
        
        data = json.loads(raw)
        used = data.get("used", [])
        return sum(1 for u in used if not u)
    except (RedisError, json.JSONDecodeError):
        return 0


def calculate_risk_score(
    user: str,
    client_ip: str,
    user_agent: Optional[str] = None,
    time_since_last_login: Optional[float] = None,
) -> float:
    """
    Calculate risk score for authentication attempt.
    
    Risk factors:
    - New IP address (0.3)
    - New user agent (0.2)
    - Long time since last login (0.2)
    - Recent failed attempts (0.3)
    
    Args:
        user: Username
        client_ip: Client IP address
        user_agent: User agent string
        time_since_last_login: Seconds since last successful login
        
    Returns:
        Risk score between 0.0 (low risk) and 1.0 (high risk)
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        # Default to medium risk if Redis unavailable
        return 0.5
    
    risk_score = 0.0
    
    try:
        # Check if IP is new (not seen in last 30 days)
        ip_key = tenant_key(f"mfa:known_ip:{user}:{hashlib.sha256(client_ip.encode()).hexdigest()}")
        if not redis_conn.exists(ip_key):
            risk_score += 0.3
            # Store this IP for future checks
            redis_conn.set(ip_key, "1", ex=30 * 24 * 3600)
        
        # Check user agent if provided
        if user_agent:
            ua_key = tenant_key(f"mfa:known_ua:{user}:{hashlib.sha256(user_agent.encode()).hexdigest()}")
            if not redis_conn.exists(ua_key):
                risk_score += 0.2
                redis_conn.set(ua_key, "1", ex=30 * 24 * 3600)
        
        # Check time since last login
        if time_since_last_login is not None:
            if time_since_last_login > 30 * 24 * 3600:  # More than 30 days
                risk_score += 0.2
            elif time_since_last_login > 7 * 24 * 3600:  # More than 7 days
                risk_score += 0.1
        
        # Check recent failed attempts
        attempts_key = _mfa_attempts_key(user)
        failed_attempts = int(redis_conn.get(attempts_key) or 0)
        if failed_attempts > 0:
            risk_score += min(0.3, failed_attempts * 0.1)
        
        return min(1.0, risk_score)
    
    except RedisError as e:
        logger.error(f"Error calculating risk score: {e}")
        return 0.5


def record_mfa_attempt(user: str, success: bool) -> None:
    """
    Record an MFA attempt (success or failure).
    
    Args:
        user: Username
        success: True if attempt was successful
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        return
    
    try:
        attempts_key = _mfa_attempts_key(user)
        if success:
            # Clear failed attempts on success
            redis_conn.delete(attempts_key)
            # Update last login time
            last_login_key = tenant_key(f"mfa:last_login:{user}")
            redis_conn.set(last_login_key, str(time.time()), ex=90 * 24 * 3600)
        else:
            # Increment failed attempts
            count = redis_conn.incr(attempts_key)
            if count == 1:
                redis_conn.expire(attempts_key, 3600)  # Expire in 1 hour
    except RedisError as e:
        logger.error(f"Error recording MFA attempt: {e}")


def get_last_login_time(user: str) -> Optional[float]:
    """
    Get the timestamp of the last successful login for a user.
    
    Args:
        user: Username
        
    Returns:
        Unix timestamp of last login, or None if not found
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        return None
    
    try:
        last_login_key = tenant_key(f"mfa:last_login:{user}")
        timestamp = redis_conn.get(last_login_key)
        return float(timestamp) if timestamp else None
    except (RedisError, ValueError):
        return None


def requires_additional_verification(risk_score: float) -> bool:
    """
    Determine if additional verification is required based on risk score.
    
    Args:
        risk_score: Risk score between 0.0 and 1.0
        
    Returns:
        True if additional verification (e.g., email, SMS) is required
    """
    return risk_score >= RISK_THRESHOLD_HIGH


def is_trusted_device(user: str, device_id: str) -> bool:
    """
    Check if a device is trusted for the user.
    
    Args:
        user: Username
        device_id: Device identifier
        
    Returns:
        True if device is trusted
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        return False
    
    try:
        return redis_conn.exists(_trusted_device_key(user, device_id)) > 0
    except RedisError:
        return False


def trust_device(user: str, device_id: str, ttl: int = 30 * 24 * 3600) -> bool:
    """
    Mark a device as trusted for the user.
    
    Args:
        user: Username
        device_id: Device identifier
        ttl: Time to live in seconds (default: 30 days)
        
    Returns:
        True if successful
    """
    redis_conn = get_redis_connection()
    if not redis_conn:
        return False
    
    try:
        redis_conn.set(_trusted_device_key(user, device_id), "1", ex=ttl)
        return True
    except RedisError as e:
        logger.error(f"Failed to trust device: {e}")
        return False
