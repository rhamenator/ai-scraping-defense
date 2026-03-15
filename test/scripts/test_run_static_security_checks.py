from __future__ import annotations

import pytest

from scripts.security.run_static_security_checks import _matches_required_value


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ("no-new-privileges:true", "no-new-privileges:true"),
        (
            "no-new-privileges:${NO_NEW_PRIVILEGES:-true}",
            "no-new-privileges:true",
        ),
        ("ALL", "ALL"),
    ],
)
def test_matches_required_value_accepts_expected_hardening_tokens(
    actual: str, expected: str
) -> None:
    assert _matches_required_value(actual, expected)


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ("no-new-privileges:false", "no-new-privileges:true"),
        (
            "no-new-privileges:${NO_NEW_PRIVILEGES:-false}",
            "no-new-privileges:true",
        ),
        ("cap-drop:ALL", "ALL"),
    ],
)
def test_matches_required_value_rejects_weakened_or_mismatched_tokens(
    actual: str, expected: str
) -> None:
    assert not _matches_required_value(actual, expected)
