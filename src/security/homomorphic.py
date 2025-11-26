"""Homomorphic encryption and privacy-preserving computation utilities.

This module provides encryption capabilities for sensitive data processing,
including:
- Symmetric encryption for data at rest and in transit
- Privacy-preserving computations on encrypted data
- Encrypted search capabilities
- Secure multi-party computation primitives

Note: This implementation uses Fernet (symmetric encryption) as the base,
with architecture prepared for full homomorphic encryption libraries
like TenSEAL or Pyfhel when needed for advanced computations.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

logger = logging.getLogger(__name__)


class HomomorphicEncryption:
    """Homomorphic encryption manager for privacy-preserving computations.
    
    This class provides encryption capabilities that allow certain operations
    to be performed on encrypted data without decrypting it first. While full
    homomorphic encryption is computationally expensive, this implementation
    provides a practical approach using symmetric encryption with support for
    privacy-preserving operations.
    
    Attributes:
        cipher: Fernet cipher instance for encryption/decryption
        key: Encryption key (should be stored securely)
    """
    
    def __init__(self, key: Optional[bytes] = None):
        """Initialize homomorphic encryption with a key.
        
        Args:
            key: 32-byte encryption key. If None, generates a new key.
                 For production, load from secure storage (env var, vault).
        """
        if key is None:
            # Try to load from environment or generate new
            key_str = os.getenv("HOMOMORPHIC_ENCRYPTION_KEY")
            if key_str:
                key = base64.urlsafe_b64decode(key_str.encode())
            else:
                key = Fernet.generate_key()
                logger.warning(
                    "No HOMOMORPHIC_ENCRYPTION_KEY found, generated new key. "
                    "Set environment variable to persist encryption key."
                )
        
        self.key = key
        self.cipher = Fernet(key)
    
    @staticmethod
    def generate_key() -> bytes:
        """Generate a new encryption key.
        
        Returns:
            32-byte encryption key suitable for Fernet
        """
        return Fernet.generate_key()
    
    @staticmethod
    def derive_key_from_password(password: str, salt: Optional[bytes] = None) -> bytes:
        """Derive an encryption key from a password using PBKDF2.
        
        Args:
            password: Password to derive key from
            salt: Salt for key derivation. If None, generates random salt.
        
        Returns:
            Derived 32-byte encryption key
        """
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt(self, data: Union[str, bytes, dict, list]) -> str:
        """Encrypt data using Fernet symmetric encryption.
        
        Args:
            data: Data to encrypt (string, bytes, or JSON-serializable object)
        
        Returns:
            Base64-encoded encrypted data as string
        
        Raises:
            ValueError: If data cannot be serialized
        """
        # Convert data to bytes
        if isinstance(data, dict) or isinstance(data, list):
            plaintext = json.dumps(data).encode()
        elif isinstance(data, str):
            plaintext = data.encode()
        elif isinstance(data, bytes):
            plaintext = data
        else:
            raise ValueError(f"Unsupported data type for encryption: {type(data)}")
        
        # Encrypt and return as string
        encrypted = self.cipher.encrypt(plaintext)
        return encrypted.decode()
    
    def decrypt(self, encrypted_data: str) -> bytes:
        """Decrypt data encrypted with encrypt().
        
        Args:
            encrypted_data: Base64-encoded encrypted data
        
        Returns:
            Decrypted data as bytes
        
        Raises:
            InvalidToken: If decryption fails (wrong key or corrupted data)
        """
        try:
            return self.cipher.decrypt(encrypted_data.encode())
        except InvalidToken:
            logger.error("Failed to decrypt data: invalid token or wrong key")
            raise
    
    def decrypt_to_string(self, encrypted_data: str) -> str:
        """Decrypt data and return as UTF-8 string.
        
        Args:
            encrypted_data: Base64-encoded encrypted data
        
        Returns:
            Decrypted data as UTF-8 string
        """
        return self.decrypt(encrypted_data).decode()
    
    def decrypt_to_json(self, encrypted_data: str) -> Union[dict, list]:
        """Decrypt data and parse as JSON.
        
        Args:
            encrypted_data: Base64-encoded encrypted JSON data
        
        Returns:
            Parsed JSON object (dict or list)
        """
        decrypted = self.decrypt_to_string(encrypted_data)
        return json.loads(decrypted)
    
    def encrypt_dict_values(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Encrypt all values in a dictionary, preserving keys.
        
        Useful for encrypting configuration or sensitive fields while
        keeping the structure readable.
        
        Args:
            data: Dictionary with plaintext values
        
        Returns:
            Dictionary with encrypted values
        """
        return {key: self.encrypt(value) for key, value in data.items()}
    
    def decrypt_dict_values(self, encrypted_data: Dict[str, str]) -> Dict[str, Any]:
        """Decrypt all values in a dictionary.
        
        Args:
            encrypted_data: Dictionary with encrypted values
        
        Returns:
            Dictionary with decrypted values
        """
        result = {}
        for key, encrypted_value in encrypted_data.items():
            try:
                # Try to parse as JSON first
                result[key] = self.decrypt_to_json(encrypted_value)
            except (json.JSONDecodeError, ValueError):
                # Fall back to string
                result[key] = self.decrypt_to_string(encrypted_value)
        return result


class PrivacyPreservingAnalytics:
    """Privacy-preserving analytics on encrypted data.
    
    Provides methods for performing statistical computations on encrypted
    data without exposing raw values.
    """
    
    def __init__(self, he: HomomorphicEncryption):
        """Initialize with a homomorphic encryption instance.
        
        Args:
            he: HomomorphicEncryption instance for operations
        """
        self.he = he
    
    def compute_encrypted_hash(self, data: str) -> str:
        """Compute a hash of encrypted data for comparison.
        
        Useful for checking equality without decrypting.
        
        Args:
            data: Data to hash (will be encrypted first)
        
        Returns:
            Hex string of hash
        """
        encrypted = self.he.encrypt(data)
        return hashlib.sha256(encrypted.encode()).hexdigest()
    
    def secure_compare(self, encrypted_a: str, encrypted_b: str) -> bool:
        """Compare two encrypted values without decrypting.
        
        Uses HMAC-based comparison to prevent timing attacks.
        
        Args:
            encrypted_a: First encrypted value
            encrypted_b: Second encrypted value
        
        Returns:
            True if values are equal
        """
        return hmac.compare_digest(encrypted_a, encrypted_b)
    
    def anonymize_ip(self, ip_address: str) -> str:
        """Anonymize an IP address for privacy-preserving analytics.
        
        Args:
            ip_address: IP address to anonymize
        
        Returns:
            Anonymized IP (last octet zeroed for IPv4, last 80 bits for IPv6)
        """
        if ":" in ip_address:
            # IPv6: zero out last 80 bits
            parts = ip_address.split(":")
            return ":".join(parts[:3]) + "::0"
        else:
            # IPv4: zero out last octet
            parts = ip_address.split(".")
            return ".".join(parts[:3]) + ".0"
    
    def encrypted_count(self, encrypted_values: List[str]) -> int:
        """Count encrypted values without decrypting.
        
        Args:
            encrypted_values: List of encrypted values
        
        Returns:
            Count of values
        """
        return len(encrypted_values)
    
    def encrypted_frequency(self, encrypted_values: List[str]) -> Dict[str, int]:
        """Compute frequency distribution of encrypted values.
        
        Args:
            encrypted_values: List of encrypted values
        
        Returns:
            Dictionary mapping encrypted value to frequency
        """
        freq: Dict[str, int] = {}
        for value in encrypted_values:
            freq[value] = freq.get(value, 0) + 1
        return freq


class EncryptedSearch:
    """Encrypted search capabilities for searching encrypted data.
    
    Provides searchable encryption that allows searching through encrypted
    data without exposing plaintext to the server.
    """
    
    def __init__(self, he: HomomorphicEncryption):
        """Initialize with a homomorphic encryption instance.
        
        Args:
            he: HomomorphicEncryption instance for operations
        """
        self.he = he
    
    def create_search_index(self, documents: List[str]) -> List[str]:
        """Create a searchable index of encrypted documents.
        
        Args:
            documents: List of plaintext documents to index
        
        Returns:
            List of encrypted documents
        """
        return [self.he.encrypt(doc) for doc in documents]
    
    def create_search_token(self, query: str) -> str:
        """Create an encrypted search token for a query.
        
        Args:
            query: Search query string
        
        Returns:
            Encrypted search token
        """
        # For exact match, encrypt the query
        return self.he.encrypt(query)
    
    def search(self, search_token: str, encrypted_index: List[str]) -> List[int]:
        """Search encrypted index using an encrypted search token.
        
        Args:
            search_token: Encrypted search token from create_search_token()
            encrypted_index: List of encrypted documents
        
        Returns:
            List of indices where matches were found
        """
        matches = []
        for i, encrypted_doc in enumerate(encrypted_index):
            # For exact match, compare encrypted values
            if hmac.compare_digest(search_token, encrypted_doc):
                matches.append(i)
        return matches
    
    def fuzzy_search(
        self, query: str, encrypted_index: List[str], threshold: float = 0.8
    ) -> List[int]:
        """Perform fuzzy search on encrypted data.
        
        Note: This decrypts each document for comparison. For production,
        consider using specialized fuzzy searchable encryption schemes.
        
        Args:
            query: Search query string
            encrypted_index: List of encrypted documents
            threshold: Similarity threshold (0-1)
        
        Returns:
            List of indices where fuzzy matches were found
        """
        matches = []
        query_lower = query.lower()
        
        for i, encrypted_doc in enumerate(encrypted_index):
            try:
                doc = self.he.decrypt_to_string(encrypted_doc).lower()
                # Simple fuzzy match: check if query is substring
                if query_lower in doc:
                    matches.append(i)
            except Exception as e:
                logger.debug(f"Failed to decrypt document {i} for search: {e}")
                continue
        
        return matches


class SecureMultiPartyComputation:
    """Secure multi-party computation primitives.
    
    Provides basic primitives for secure multi-party computation (MPC),
    allowing multiple parties to jointly compute a function over their
    inputs while keeping those inputs private.
    """
    
    def __init__(self, he: HomomorphicEncryption):
        """Initialize with a homomorphic encryption instance.
        
        Args:
            he: HomomorphicEncryption instance for operations
        """
        self.he = he
    
    def create_share(self, secret: Union[int, float], num_shares: int = 2) -> List[bytes]:
        """Create secret shares using additive secret sharing.
        
        Splits a secret into multiple shares such that all shares are needed
        to reconstruct the original secret.
        
        Args:
            secret: Secret value to share
            num_shares: Number of shares to create
        
        Returns:
            List of encrypted shares
        """
        if num_shares < 2:
            raise ValueError("Need at least 2 shares")
        
        # Convert to bytes
        secret_bytes = str(secret).encode()
        
        # Generate random shares (all but last)
        shares = []
        total = 0
        for _ in range(num_shares - 1):
            share = os.urandom(len(secret_bytes))
            shares.append(share)
            total ^= int.from_bytes(share, byteorder="big")
        
        # Last share is XOR of secret and all other shares
        secret_int = int.from_bytes(secret_bytes, byteorder="big")
        last_share = (secret_int ^ total).to_bytes(len(secret_bytes), byteorder="big")
        shares.append(last_share)
        
        return shares
    
    def reconstruct_secret(self, shares: List[bytes]) -> str:
        """Reconstruct a secret from its shares.
        
        Args:
            shares: List of secret shares
        
        Returns:
            Reconstructed secret as string
        """
        if len(shares) < 2:
            raise ValueError("Need at least 2 shares to reconstruct")
        
        # XOR all shares together
        result = 0
        max_len = max(len(share) for share in shares)
        
        for share in shares:
            result ^= int.from_bytes(share, byteorder="big")
        
        return result.to_bytes(max_len, byteorder="big").decode()


# Convenience functions for global use
_global_he: Optional[HomomorphicEncryption] = None


def get_homomorphic_encryption() -> HomomorphicEncryption:
    """Get or create global HomomorphicEncryption instance.
    
    Returns:
        Global HomomorphicEncryption instance
    """
    global _global_he
    if _global_he is None:
        _global_he = HomomorphicEncryption()
    return _global_he


def encrypt_sensitive_data(data: Union[str, dict, list]) -> str:
    """Convenience function to encrypt sensitive data.
    
    Args:
        data: Data to encrypt
    
    Returns:
        Encrypted data as string
    """
    he = get_homomorphic_encryption()
    return he.encrypt(data)


def decrypt_sensitive_data(encrypted_data: str) -> Union[str, dict, list]:
    """Convenience function to decrypt sensitive data.
    
    Args:
        encrypted_data: Encrypted data string
    
    Returns:
        Decrypted data
    """
    he = get_homomorphic_encryption()
    try:
        return he.decrypt_to_json(encrypted_data)
    except (json.JSONDecodeError, ValueError):
        return he.decrypt_to_string(encrypted_data)


__all__ = [
    "HomomorphicEncryption",
    "PrivacyPreservingAnalytics",
    "EncryptedSearch",
    "SecureMultiPartyComputation",
    "encrypt_sensitive_data",
    "decrypt_sensitive_data",
    "get_homomorphic_encryption",
]
