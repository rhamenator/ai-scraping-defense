"""Load a pickle-based model only when its bytes match a trusted digest."""

import hashlib
import io
import re
from pathlib import Path

import joblib

MAX_MODEL_BYTES = 100 * 1024 * 1024


def load_verified_joblib(path: str, expected_sha256: str):
    """Verify the exact bytes that joblib will deserialize.

    The digest must come from deployment configuration, not a sidecar beside the
    model. A matching digest authenticates the artifact; it does not make pickle
    intrinsically safe for artifacts from untrusted publishers.
    """
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256 or ""):
        raise ValueError("A trusted 64-character model SHA-256 is required")
    with Path(path).open("rb") as model_file:
        payload = model_file.read(MAX_MODEL_BYTES + 1)
    if len(payload) > MAX_MODEL_BYTES:
        raise ValueError("Model exceeds the 100 MiB size limit")
    if hashlib.sha256(payload).hexdigest() != expected_sha256.lower():
        raise ValueError("Model SHA-256 does not match the trusted digest")
    return joblib.load(io.BytesIO(payload))
