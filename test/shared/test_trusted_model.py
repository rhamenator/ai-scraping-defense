import hashlib
from pathlib import Path

import joblib
import pytest

from src.shared.trusted_model import load_verified_joblib


class _MaliciousModel:
    def __init__(self, sentinel):
        self.sentinel = sentinel

    def __reduce__(self):
        return (Path.touch, (self.sentinel,))


def test_untrusted_model_bytes_are_never_deserialized(tmp_path):
    model_path = tmp_path / "model.joblib"
    sentinel = tmp_path / "executed"
    joblib.dump(_MaliciousModel(sentinel), model_path)
    # The digest is deliberately wrong, so deserialization must not occur.
    with pytest.raises(ValueError, match="does not match"):
        load_verified_joblib(str(model_path), "0" * 64)
    if sentinel.exists():
        pytest.fail("Untrusted model bytes were deserialized")


def test_verified_model_loads(tmp_path):
    model_path = tmp_path / "model.joblib"
    joblib.dump({"answer": 42}, model_path)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if load_verified_joblib(str(model_path), digest) != {"answer": 42}:
        pytest.fail("Verified model did not load")


def test_missing_trusted_digest_fails_closed(tmp_path):
    model_path = tmp_path / "model.joblib"
    joblib.dump({"answer": 42}, model_path)
    with pytest.raises(ValueError, match="SHA-256 is required"):
        load_verified_joblib(str(model_path), "")
