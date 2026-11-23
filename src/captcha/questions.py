"""Accessible, text-only CAPTCHA question generators (#1903 backlog).

Every question type is screen-reader readable, can be read aloud via the browser's
``speechSynthesis`` API, and shares the same one-attempt, rate-limit, minimum-solve-time,
and client-proof protections so bots cannot bypass controls by picking an easier type.
"""

import hmac
import secrets

QUESTION_TYPES: tuple[str, ...] = ("math", "color", "word")

_COLOR_WORDS: tuple[str, ...] = (
    "amber",
    "azure",
    "crimson",
    "emerald",
    "indigo",
    "magenta",
    "orange",
    "purple",
    "scarlet",
    "silver",
    "violet",
    "yellow",
)

_DECOY_WORDS: tuple[str, ...] = (
    "anchor",
    "basket",
    "breeze",
    "bridge",
    "candle",
    "canyon",
    "castle",
    "clover",
    "compass",
    "feather",
    "forest",
    "garden",
    "glacier",
    "harbor",
    "horizon",
    "island",
    "kettle",
    "lantern",
    "meadow",
    "mirror",
    "mountain",
    "pebble",
    "pillow",
    "planet",
    "river",
    "saddle",
    "shadow",
    "shelter",
    "summit",
    "temple",
    "timber",
    "valley",
    "velvet",
    "window",
)


def normalize_question_type(question_type: str | None) -> str:
    """Return a supported question type, defaulting to ``math``."""
    candidate = (question_type or "math").strip().lower()
    return candidate if candidate in QUESTION_TYPES else "math"


def generate_question(question_type: str | None) -> tuple[str, str, str]:
    """Return ``(normalized_type, prompt_text, expected_answer)`` for the visitor."""
    qtype = normalize_question_type(question_type)
    if qtype == "color":
        color = secrets.choice(_COLOR_WORDS)
        decoys = _pick_distinct(_DECOY_WORDS, 5)
        choices = [color, *decoys]
        _secure_shuffle(choices)
        prompt = f"Which of these words is a colour? {', '.join(choices)}"
        return qtype, prompt, color
    if qtype == "word":
        word = secrets.choice(_DECOY_WORDS)
        return qtype, f"Type this word to continue: {word}", word
    a = secrets.randbelow(8) + 2
    b = secrets.randbelow(8) + 2
    return "math", f"What is {a} + {b}?", str(a + b)


def answers_match(expected: str, supplied: str) -> bool:
    """Constant-time, case-insensitive comparison of the visitor's answer."""
    left = (expected or "").strip().lower().encode("utf-8")
    right = (supplied or "").strip().lower().encode("utf-8")
    return bool(left) and hmac.compare_digest(left, right)


def _pick_distinct(pool: tuple[str, ...], count: int) -> list[str]:
    remaining = list(pool)
    picked: list[str] = []
    for _ in range(min(count, len(remaining))):
        idx = secrets.randbelow(len(remaining))
        picked.append(remaining.pop(idx))
    return picked


def _secure_shuffle(items: list[str]) -> None:
    for idx in range(len(items) - 1, 0, -1):
        swap = secrets.randbelow(idx + 1)
        items[idx], items[swap] = items[swap], items[idx]
