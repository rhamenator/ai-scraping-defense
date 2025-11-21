"""
Post-Quantum Cryptography module for quantum-resistant security.

This module provides quantum-resistant cryptographic operations including:
- Quantum-safe key exchange (KEM)
- Quantum-safe digital signatures
- Crypto-agility support for transitioning to PQC algorithms
- Hybrid classical+quantum schemes for backward compatibility
"""

import logging
import os
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Flag to indicate if PQC libraries are available
PQC_AVAILABLE = False
try:
    import oqs  # type: ignore
    PQC_AVAILABLE = True
except ImportError:
    logger.warning(
        "liboqs not available. Post-quantum cryptography will be disabled. "
        "Install with: pip install oqs"
    )
    oqs = None  # type: ignore


class PQCAlgorithm(Enum):
    """Enumeration of supported post-quantum cryptographic algorithms."""
    # NIST-standardized KEM (Key Encapsulation Mechanism)
    KYBER512 = "Kyber512"
    KYBER768 = "Kyber768"
    KYBER1024 = "Kyber1024"
    
    # NIST-standardized signatures
    DILITHIUM2 = "Dilithium2"
    DILITHIUM3 = "Dilithium3"
    DILITHIUM5 = "Dilithium5"
    
    # Additional NIST candidates
    FALCON512 = "Falcon-512"
    FALCON1024 = "Falcon-1024"
    
    # Hybrid mode (classical + quantum)
    HYBRID_X25519_KYBER768 = "hybrid_x25519_kyber768"


def is_pqc_enabled() -> bool:
    """Check if post-quantum cryptography is enabled via environment variable."""
    return os.getenv("ENABLE_PQC", "false").lower() == "true" and PQC_AVAILABLE


def get_default_kem_algorithm() -> str:
    """Get the default KEM algorithm from environment or use Kyber768."""
    default = PQCAlgorithm.KYBER768.value
    return os.getenv("PQC_KEM_ALGORITHM", default)


def get_default_signature_algorithm() -> str:
    """Get the default signature algorithm from environment or use Dilithium3."""
    default = PQCAlgorithm.DILITHIUM3.value
    return os.getenv("PQC_SIGNATURE_ALGORITHM", default)


class QuantumSafeKEM:
    """
    Quantum-safe Key Encapsulation Mechanism.
    
    Uses NIST-standardized Kyber algorithm for quantum-resistant key exchange.
    """
    
    def __init__(self, algorithm: Optional[str] = None):
        """
        Initialize quantum-safe KEM with specified algorithm.
        
        Args:
            algorithm: PQC algorithm name (e.g., 'Kyber768'). If None, uses default.
        """
        if not PQC_AVAILABLE:
            raise RuntimeError(
                "Post-quantum cryptography not available. Install liboqs: pip install oqs"
            )
        
        self.algorithm = algorithm or get_default_kem_algorithm()
        try:
            self.kem = oqs.KeyEncapsulation(self.algorithm)
        except Exception as e:
            logger.error("Failed to initialize KEM with algorithm %s: %s", self.algorithm, e)
            raise
        
        logger.info("Initialized quantum-safe KEM with algorithm: %s", self.algorithm)
    
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """
        Generate a quantum-safe public/private key pair.
        
        Returns:
            Tuple of (public_key, secret_key) as bytes
        """
        public_key = self.kem.generate_keypair()
        secret_key = self.kem.export_secret_key()
        return public_key, secret_key
    
    def encapsulate(self, public_key: bytes) -> Tuple[bytes, bytes]:
        """
        Encapsulate a shared secret using recipient's public key.
        
        Args:
            public_key: Recipient's public key
            
        Returns:
            Tuple of (ciphertext, shared_secret)
        """
        ciphertext, shared_secret = self.kem.encap_secret(public_key)
        return ciphertext, shared_secret
    
    def decapsulate(self, ciphertext: bytes, secret_key: bytes) -> bytes:
        """
        Decapsulate the shared secret using ciphertext and private key.
        
        Args:
            ciphertext: Encapsulated ciphertext
            secret_key: Recipient's secret key
            
        Returns:
            Shared secret
        """
        self.kem = oqs.KeyEncapsulation(self.algorithm, secret_key)
        shared_secret = self.kem.decap_secret(ciphertext)
        return shared_secret


class QuantumSafeSignature:
    """
    Quantum-safe digital signature scheme.
    
    Uses NIST-standardized Dilithium algorithm for quantum-resistant signatures.
    """
    
    def __init__(self, algorithm: Optional[str] = None):
        """
        Initialize quantum-safe signature with specified algorithm.
        
        Args:
            algorithm: PQC signature algorithm (e.g., 'Dilithium3'). If None, uses default.
        """
        if not PQC_AVAILABLE:
            raise RuntimeError(
                "Post-quantum cryptography not available. Install liboqs: pip install oqs"
            )
        
        self.algorithm = algorithm or get_default_signature_algorithm()
        try:
            self.signer = oqs.Signature(self.algorithm)
        except Exception as e:
            logger.error("Failed to initialize signature with algorithm %s: %s", self.algorithm, e)
            raise
        
        logger.info("Initialized quantum-safe signature with algorithm: %s", self.algorithm)
    
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """
        Generate a quantum-safe signing key pair.
        
        Returns:
            Tuple of (public_key, secret_key) as bytes
        """
        public_key = self.signer.generate_keypair()
        secret_key = self.signer.export_secret_key()
        return public_key, secret_key
    
    def sign(self, message: bytes, secret_key: bytes) -> bytes:
        """
        Sign a message using quantum-safe signature.
        
        Args:
            message: Message to sign
            secret_key: Signer's secret key
            
        Returns:
            Signature bytes
        """
        self.signer = oqs.Signature(self.algorithm, secret_key)
        signature = self.signer.sign(message)
        return signature
    
    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        """
        Verify a quantum-safe signature.
        
        Args:
            message: Original message
            signature: Signature to verify
            public_key: Signer's public key
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            self.signer = oqs.Signature(self.algorithm)
            is_valid = self.signer.verify(message, signature, public_key)
            return is_valid
        except Exception as e:
            logger.warning("Signature verification failed: %s", e)
            return False


class CryptoAgility:
    """
    Crypto-agility manager for smooth transition to post-quantum algorithms.
    
    Supports:
    - Algorithm negotiation
    - Hybrid classical+quantum modes
    - Fallback to classical algorithms
    - Algorithm version tracking
    """
    
    SUPPORTED_ALGORITHMS = [
        "classical",  # Traditional RSA/ECC
        "pqc",        # Pure post-quantum
        "hybrid"      # Hybrid classical+quantum
    ]
    
    @staticmethod
    def get_crypto_mode() -> str:
        """
        Get current cryptographic mode from environment.
        
        Returns:
            One of: 'classical', 'pqc', 'hybrid'
        """
        mode = os.getenv("CRYPTO_MODE", "classical").lower()
        if mode not in CryptoAgility.SUPPORTED_ALGORITHMS:
            logger.warning(
                "Invalid CRYPTO_MODE '%s', falling back to 'classical'", mode
            )
            return "classical"
        return mode
    
    @staticmethod
    def should_use_pqc() -> bool:
        """Check if post-quantum cryptography should be used."""
        mode = CryptoAgility.get_crypto_mode()
        return mode in ("pqc", "hybrid") and is_pqc_enabled()
    
    @staticmethod
    def should_use_hybrid() -> bool:
        """Check if hybrid classical+quantum mode should be used."""
        return CryptoAgility.get_crypto_mode() == "hybrid" and is_pqc_enabled()


def assess_quantum_threat_level() -> str:
    """
    Assess current quantum threat level based on configuration.
    
    Returns:
        Threat level: 'low', 'medium', 'high', or 'critical'
    """
    # Check if dealing with long-term secrets that need future protection
    protect_long_term = os.getenv("PQC_PROTECT_LONG_TERM_SECRETS", "false").lower() == "true"
    
    # Check if high-value data is being protected
    high_value_data = os.getenv("PQC_HIGH_VALUE_DATA", "false").lower() == "true"
    
    # Check quantum computer development timeline awareness
    quantum_timeline_years = int(os.getenv("PQC_QUANTUM_THREAT_TIMELINE_YEARS", "10"))
    
    if protect_long_term and high_value_data:
        return "critical"
    elif protect_long_term or high_value_data:
        return "high"
    elif quantum_timeline_years <= 5:
        return "high"
    elif quantum_timeline_years <= 10:
        return "medium"
    else:
        return "low"


def generate_pqc_keypair(
    algorithm_type: str = "kem"
) -> Optional[Tuple[bytes, bytes]]:
    """
    Generate a post-quantum cryptographic key pair.
    
    Args:
        algorithm_type: Either 'kem' for key exchange or 'signature' for signing
        
    Returns:
        Tuple of (public_key, secret_key) or None if PQC not available
    """
    if not is_pqc_enabled():
        logger.info("PQC not enabled, skipping quantum-safe key generation")
        return None
    
    try:
        if algorithm_type == "kem":
            kem = QuantumSafeKEM()
            return kem.generate_keypair()
        elif algorithm_type == "signature":
            signer = QuantumSafeSignature()
            return signer.generate_keypair()
        else:
            raise ValueError(f"Unknown algorithm type: {algorithm_type}")
    except Exception as e:
        logger.error("Failed to generate PQC keypair: %s", e)
        return None
