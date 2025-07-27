"""Generate endless labyrinth pages for bots."""
from __future__ import annotations

import hashlib
import random


def generate_labyrinth_page(seed: str, depth: int = 5) -> str:
    random.seed(seed)
    links = []
    for i in range(depth):
        token = hashlib.sha256(f"{seed}-{i}".encode()).hexdigest()[:8]
        links.append(f"/tarpit/{token}")
    random.shuffle(links)
    body = "".join(f"<a href='{link}'>Next</a><br/>" for link in links)
    return f"<html><head><title>Loading...</title></head><body>{body}</body></html>"
