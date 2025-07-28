"""Generate endless labyrinth pages for bots."""

from __future__ import annotations

import hashlib
import os
import random

from .obfuscation import (
    generate_fingerprinting_script,
    generate_obfuscated_css,
    generate_obfuscated_js,
)


def generate_labyrinth_page(seed: str, depth: int = 5) -> str:
    random.seed(seed)
    links = []
    for i in range(depth):
        token = hashlib.sha256(f"{seed}-{i}".encode()).hexdigest()[:8]
        links.append(f"/tarpit/{token}")
    random.shuffle(links)
    body = "".join(f"<a href='{link}'>Next</a><br/>" for link in links)
    css = generate_obfuscated_css()
    js = generate_obfuscated_js()
    fp = ""
    if os.getenv("ENABLE_FINGERPRINTING", "false").lower() == "true":
        fp = generate_fingerprinting_script()
    return (
        "<html><head><title>Loading...</title>" + css + "</head>"
        "<body>" + body + js + fp + "</body></html>"
    )
