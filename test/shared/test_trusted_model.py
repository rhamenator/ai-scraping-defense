import hashlib
import pickle
from pathlib import Path

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
    model_path.write_bytes(pickle.dumps(_MaliciousModel(sentinel)))
    # The digest is deliberately wrong, so deserialization must not occur.
    with pytest.raises(ValueError, match="does not match"):
        load_verified_joblib(str(model_path), "0" * 64)
    assert not sentinel.exists()


def test_verified_model_loads(tmp_path):
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(pickle.dumps({"answer": 42}))
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    assert load_verified_joblib(str(model_path), digest) == {"answer": 42}


def test_missing_trusted_digest_fails_closed(tmp_path):
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(pickle.dumps({"answer": 42}))
    with pytest.raises(ValueError, match="SHA-256 is required"):
        load_verified_joblib(str(model_path), "")
