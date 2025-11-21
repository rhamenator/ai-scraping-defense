"""Tests for post-quantum cryptography module."""

import os
from unittest.mock import patch

import pytest

from src.shared import quantum_crypto


class TestPQCAvailability:
    """Test PQC library availability checks."""

    def test_pqc_available_flag(self):
        """Test that PQC_AVAILABLE flag is set correctly."""
        # Should be True if oqs is installed, False otherwise
        assert isinstance(quantum_crypto.PQC_AVAILABLE, bool)

    @patch.dict(os.environ, {"ENABLE_PQC": "true"})
    def test_is_pqc_enabled_true(self):
        """Test PQC enabled when environment variable is set."""
        if quantum_crypto.PQC_AVAILABLE:
            assert quantum_crypto.is_pqc_enabled() is True
        else:
            # If library not available, should still be False
            assert quantum_crypto.is_pqc_enabled() is False

    @patch.dict(os.environ, {"ENABLE_PQC": "false"})
    def test_is_pqc_enabled_false(self):
        """Test PQC disabled when environment variable is false."""
        assert quantum_crypto.is_pqc_enabled() is False


class TestAlgorithmConfiguration:
    """Test algorithm configuration retrieval."""

    @patch.dict(os.environ, {"PQC_KEM_ALGORITHM": "Kyber1024"})
    def test_get_default_kem_algorithm_custom(self):
        """Test custom KEM algorithm from environment."""
        assert quantum_crypto.get_default_kem_algorithm() == "Kyber1024"

    def test_get_default_kem_algorithm_default(self):
        """Test default KEM algorithm."""
        with patch.dict(os.environ, {}, clear=True):
            assert quantum_crypto.get_default_kem_algorithm() == "Kyber768"

    @patch.dict(os.environ, {"PQC_SIGNATURE_ALGORITHM": "Dilithium5"})
    def test_get_default_signature_algorithm_custom(self):
        """Test custom signature algorithm from environment."""
        assert quantum_crypto.get_default_signature_algorithm() == "Dilithium5"

    def test_get_default_signature_algorithm_default(self):
        """Test default signature algorithm."""
        with patch.dict(os.environ, {}, clear=True):
            assert quantum_crypto.get_default_signature_algorithm() == "Dilithium3"


@pytest.mark.skipif(
    not quantum_crypto.PQC_AVAILABLE,
    reason="liboqs not installed"
)
class TestQuantumSafeKEM:
    """Test Quantum-safe Key Encapsulation Mechanism."""

    def test_kem_initialization(self):
        """Test KEM initialization with default algorithm."""
        kem = quantum_crypto.QuantumSafeKEM()
        assert kem.algorithm == quantum_crypto.get_default_kem_algorithm()

    def test_kem_initialization_custom_algorithm(self):
        """Test KEM initialization with custom algorithm."""
        kem = quantum_crypto.QuantumSafeKEM(algorithm="Kyber512")
        assert kem.algorithm == "Kyber512"

    def test_generate_keypair(self):
        """Test quantum-safe keypair generation."""
        kem = quantum_crypto.QuantumSafeKEM()
        public_key, secret_key = kem.generate_keypair()
        
        assert isinstance(public_key, bytes)
        assert isinstance(secret_key, bytes)
        assert len(public_key) > 0
        assert len(secret_key) > 0

    def test_encapsulate_decapsulate_roundtrip(self):
        """Test complete KEM roundtrip: generate, encapsulate, decapsulate."""
        kem1 = quantum_crypto.QuantumSafeKEM()
        public_key, secret_key = kem1.generate_keypair()
        
        # Encapsulate with public key
        kem2 = quantum_crypto.QuantumSafeKEM()
        ciphertext, shared_secret1 = kem2.encapsulate(public_key)
        
        # Decapsulate with secret key
        kem3 = quantum_crypto.QuantumSafeKEM()
        shared_secret2 = kem3.decapsulate(ciphertext, secret_key)
        
        # Both parties should have the same shared secret
        assert shared_secret1 == shared_secret2
        assert len(shared_secret1) > 0


@pytest.mark.skipif(
    not quantum_crypto.PQC_AVAILABLE,
    reason="liboqs not installed"
)
class TestQuantumSafeSignature:
    """Test Quantum-safe digital signatures."""

    def test_signature_initialization(self):
        """Test signature initialization with default algorithm."""
        signer = quantum_crypto.QuantumSafeSignature()
        assert signer.algorithm == quantum_crypto.get_default_signature_algorithm()

    def test_signature_initialization_custom_algorithm(self):
        """Test signature initialization with custom algorithm."""
        signer = quantum_crypto.QuantumSafeSignature(algorithm="Dilithium2")
        assert signer.algorithm == "Dilithium2"

    def test_generate_signing_keypair(self):
        """Test quantum-safe signing keypair generation."""
        signer = quantum_crypto.QuantumSafeSignature()
        public_key, secret_key = signer.generate_keypair()
        
        assert isinstance(public_key, bytes)
        assert isinstance(secret_key, bytes)
        assert len(public_key) > 0
        assert len(secret_key) > 0

    def test_sign_and_verify(self):
        """Test signing and verification of a message."""
        signer = quantum_crypto.QuantumSafeSignature()
        public_key, secret_key = signer.generate_keypair()
        
        message = b"This is a test message for quantum-safe signing"
        
        # Sign the message
        signature = signer.sign(message, secret_key)
        assert isinstance(signature, bytes)
        assert len(signature) > 0
        
        # Verify the signature
        is_valid = signer.verify(message, signature, public_key)
        assert is_valid is True

    def test_verify_invalid_signature(self):
        """Test that invalid signatures are rejected."""
        signer = quantum_crypto.QuantumSafeSignature()
        public_key, secret_key = signer.generate_keypair()
        
        message = b"Original message"
        signature = signer.sign(message, secret_key)
        
        # Try to verify with different message
        tampered_message = b"Tampered message"
        is_valid = signer.verify(tampered_message, signature, public_key)
        assert is_valid is False

    def test_verify_with_wrong_public_key(self):
        """Test that signatures don't verify with wrong public key."""
        signer1 = quantum_crypto.QuantumSafeSignature()
        public_key1, secret_key1 = signer1.generate_keypair()
        
        signer2 = quantum_crypto.QuantumSafeSignature()
        public_key2, _ = signer2.generate_keypair()
        
        message = b"Test message"
        signature = signer1.sign(message, secret_key1)
        
        # Try to verify with wrong public key
        is_valid = signer2.verify(message, signature, public_key2)
        assert is_valid is False


class TestCryptoAgility:
    """Test crypto-agility support."""

    @patch.dict(os.environ, {"CRYPTO_MODE": "classical"})
    def test_get_crypto_mode_classical(self):
        """Test classical crypto mode."""
        assert quantum_crypto.CryptoAgility.get_crypto_mode() == "classical"

    @patch.dict(os.environ, {"CRYPTO_MODE": "pqc"})
    def test_get_crypto_mode_pqc(self):
        """Test post-quantum crypto mode."""
        assert quantum_crypto.CryptoAgility.get_crypto_mode() == "pqc"

    @patch.dict(os.environ, {"CRYPTO_MODE": "hybrid"})
    def test_get_crypto_mode_hybrid(self):
        """Test hybrid crypto mode."""
        assert quantum_crypto.CryptoAgility.get_crypto_mode() == "hybrid"

    @patch.dict(os.environ, {"CRYPTO_MODE": "invalid"})
    def test_get_crypto_mode_invalid_fallback(self):
        """Test fallback to classical for invalid mode."""
        assert quantum_crypto.CryptoAgility.get_crypto_mode() == "classical"

    @patch.dict(os.environ, {"CRYPTO_MODE": "pqc", "ENABLE_PQC": "true"})
    def test_should_use_pqc(self):
        """Test PQC usage determination."""
        if quantum_crypto.PQC_AVAILABLE:
            assert quantum_crypto.CryptoAgility.should_use_pqc() is True
        else:
            assert quantum_crypto.CryptoAgility.should_use_pqc() is False

    @patch.dict(os.environ, {"CRYPTO_MODE": "classical"})
    def test_should_not_use_pqc_in_classical_mode(self):
        """Test PQC is not used in classical mode."""
        assert quantum_crypto.CryptoAgility.should_use_pqc() is False

    @patch.dict(os.environ, {"CRYPTO_MODE": "hybrid", "ENABLE_PQC": "true"})
    def test_should_use_hybrid(self):
        """Test hybrid mode detection."""
        if quantum_crypto.PQC_AVAILABLE:
            assert quantum_crypto.CryptoAgility.should_use_hybrid() is True
        else:
            assert quantum_crypto.CryptoAgility.should_use_hybrid() is False


class TestQuantumThreatAssessment:
    """Test quantum threat level assessment."""

    @patch.dict(os.environ, {
        "PQC_PROTECT_LONG_TERM_SECRETS": "true",
        "PQC_HIGH_VALUE_DATA": "true"
    })
    def test_critical_threat_level(self):
        """Test critical threat level assessment."""
        assert quantum_crypto.assess_quantum_threat_level() == "critical"

    @patch.dict(os.environ, {
        "PQC_PROTECT_LONG_TERM_SECRETS": "true",
        "PQC_HIGH_VALUE_DATA": "false"
    })
    def test_high_threat_level_long_term(self):
        """Test high threat level for long-term secrets."""
        assert quantum_crypto.assess_quantum_threat_level() == "high"

    @patch.dict(os.environ, {
        "PQC_PROTECT_LONG_TERM_SECRETS": "false",
        "PQC_HIGH_VALUE_DATA": "true"
    })
    def test_high_threat_level_high_value(self):
        """Test high threat level for high-value data."""
        assert quantum_crypto.assess_quantum_threat_level() == "high"

    @patch.dict(os.environ, {
        "PQC_PROTECT_LONG_TERM_SECRETS": "false",
        "PQC_HIGH_VALUE_DATA": "false",
        "PQC_QUANTUM_THREAT_TIMELINE_YEARS": "5"
    })
    def test_high_threat_level_timeline(self):
        """Test high threat level based on timeline."""
        assert quantum_crypto.assess_quantum_threat_level() == "high"

    @patch.dict(os.environ, {
        "PQC_PROTECT_LONG_TERM_SECRETS": "false",
        "PQC_HIGH_VALUE_DATA": "false",
        "PQC_QUANTUM_THREAT_TIMELINE_YEARS": "8"
    })
    def test_medium_threat_level(self):
        """Test medium threat level."""
        assert quantum_crypto.assess_quantum_threat_level() == "medium"

    @patch.dict(os.environ, {
        "PQC_PROTECT_LONG_TERM_SECRETS": "false",
        "PQC_HIGH_VALUE_DATA": "false",
        "PQC_QUANTUM_THREAT_TIMELINE_YEARS": "15"
    })
    def test_low_threat_level(self):
        """Test low threat level."""
        assert quantum_crypto.assess_quantum_threat_level() == "low"


class TestGeneratePQCKeypair:
    """Test high-level keypair generation function."""

    @patch.dict(os.environ, {"ENABLE_PQC": "false"})
    def test_generate_pqc_keypair_disabled(self):
        """Test keypair generation returns None when PQC disabled."""
        result = quantum_crypto.generate_pqc_keypair()
        assert result is None

    @pytest.mark.skipif(
        not quantum_crypto.PQC_AVAILABLE,
        reason="liboqs not installed"
    )
    @patch.dict(os.environ, {"ENABLE_PQC": "true"})
    def test_generate_pqc_keypair_kem(self):
        """Test KEM keypair generation."""
        result = quantum_crypto.generate_pqc_keypair(algorithm_type="kem")
        assert result is not None
        public_key, secret_key = result
        assert isinstance(public_key, bytes)
        assert isinstance(secret_key, bytes)

    @pytest.mark.skipif(
        not quantum_crypto.PQC_AVAILABLE,
        reason="liboqs not installed"
    )
    @patch.dict(os.environ, {"ENABLE_PQC": "true"})
    def test_generate_pqc_keypair_signature(self):
        """Test signature keypair generation."""
        result = quantum_crypto.generate_pqc_keypair(algorithm_type="signature")
        assert result is not None
        public_key, secret_key = result
        assert isinstance(public_key, bytes)
        assert isinstance(secret_key, bytes)

    @pytest.mark.skipif(
        not quantum_crypto.PQC_AVAILABLE,
        reason="liboqs not installed"
    )
    @patch.dict(os.environ, {"ENABLE_PQC": "true"})
    def test_generate_pqc_keypair_invalid_type(self):
        """Test keypair generation with invalid algorithm type."""
        result = quantum_crypto.generate_pqc_keypair(algorithm_type="invalid")
        assert result is None


class TestPQCNotAvailable:
    """Test behavior when PQC libraries are not available."""

    def test_kem_initialization_without_oqs(self):
        """Test KEM initialization fails gracefully without liboqs."""
        if not quantum_crypto.PQC_AVAILABLE:
            with pytest.raises(RuntimeError, match="Post-quantum cryptography not available"):
                quantum_crypto.QuantumSafeKEM()

    def test_signature_initialization_without_oqs(self):
        """Test signature initialization fails gracefully without liboqs."""
        if not quantum_crypto.PQC_AVAILABLE:
            with pytest.raises(RuntimeError, match="Post-quantum cryptography not available"):
                quantum_crypto.QuantumSafeSignature()
