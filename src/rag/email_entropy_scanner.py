# rag/email_entropy_scanner.py

import logging
import math
from collections import Counter
from typing import List

logger = logging.getLogger(__name__)


# Calculate Shannon entropy
def calculate_entropy(s: str) -> float:
    if not s:  # Handle empty strings
        return 0.0
    counts = Counter(s)
    length = len(s)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


# Detect if the email username looks suspicious based on entropy and patterns
def is_suspicious_username(username: str) -> bool:
    if not username:
        return True  # Treat empty username as suspicious

    cleaned = username.replace(".", "")
    entropy = calculate_entropy(cleaned)
    length = len(username)

    # Heuristics: high entropy, plus unusual length, high digit ratio, or no vowels
    # Adjust these thresholds based on observed patterns
    digit_ratio = sum(c.isdigit() for c in username) / length
    vowel_count = sum(c in "aeiou" for c in username.lower())

    # Flag as suspicious if entropy is high AND it meets other criteria
    suspicious_pattern = length > 12 or digit_ratio > 0.5 or vowel_count == 0
    high_entropy = entropy > 3.0

    if "." in username and digit_ratio < 0.5 and vowel_count > 0 and entropy < 4.5:
        return False

    # Additional simple heuristics
    if digit_ratio > 0.7 and length > 8:
        return True
    if vowel_count == 0 and length >= 10:
        return True

    is_suspicious = high_entropy and suspicious_pattern

    return is_suspicious


# Check if domain is in a known list of disposable email providers
def is_disposable_domain(domain: str, disposable_list: List[str]) -> bool:
    if not domain:
        return True  # Treat empty domain as suspicious
    # Convert to set for faster lookups if list is large
    disposable_set = set(d.lower() for d in disposable_list)
    return domain.lower() in disposable_set


# Main validator function combining username and domain checks
def is_suspicious_email(email: str, disposable_list: List[str]) -> bool:
    if not isinstance(email, str) or "@" not in email:
        return True  # Invalid format is suspicious

    parts = email.split("@", 1)
    if len(parts) != 2:
        return True  # Should not happen if '@' is present, but belt-and-suspenders

    username, domain = parts
    if domain.startswith(".") or domain.strip() == "":
        return True

    # Check components
    username_suspicious = is_suspicious_username(username)
    domain_disposable = is_disposable_domain(domain, disposable_list)

    return username_suspicious or domain_disposable


# Example usage block (only runs if script is executed directly)
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    # Sample disposable domains list (load from file/config in production)
    default_disposable_domains = [
        "mailinator.com",
        "tempmail.com",
        "10minutemail.com",
        "guerrillamail.com",
        "dispostable.com",
        "getairmail.com",
        "yopmail.com",
        "throwawaymail.com",
        # Add more known disposable domains here
    ]

    test_emails = [
        "jane.doe@gmail.com",  # OK
        "support@mycompany.com",  # OK
        "b394v8n93n4v@tempmail.com",  # SUSPICIOUS (Disposable Domain)
        "xg8u9h13g51@gmail.com",  # SUSPICIOUS (High Entropy + Length)
        "a.very.long.username.with.dots@outlook.com",  # OK (Low Entropy)
        "123456789012345@gmail.com",  # SUSPICIOUS (High Digit Ratio + Length)
        "sdfghjklmnbvcxz@yahoo.com",  # SUSPICIOUS (No Vowels + High Entropy + Length)
        "shorty@gmail.com",  # OK
        "x1z@aol.com",  # OK (Short, low entropy)
        "x1zq@aol.com",  # OK (Short, medium entropy)
        "x1zqr@aol.com",  # OK (Short, medium entropy)
        "x1zqrs@aol.com",  # OK (Short, higher entropy but has vowel)
        "t@t.co",  # OK
        "",  # SUSPICIOUS (Invalid)
        "test@",  # SUSPICIOUS (Invalid)
        "@test.com",  # SUSPICIOUS (Invalid)
    ]

    logger.info("--- Email Suspicion Test ---")
    for email in test_emails:
        result = is_suspicious_email(email, default_disposable_domains)
        logger.info("'%s': %s", email, "SUSPICIOUS" if result else "OK")
    logger.info("----------------------------")
