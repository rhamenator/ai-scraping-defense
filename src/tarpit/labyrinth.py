from __future__ import annotations

import hashlib
import os
import random

from .obfuscation import (
    generate_fingerprinting_script,
    generate_obfuscated_css,
    generate_obfuscated_js,
)


class LinkFlyweight:
    """Flyweight for sharing the common parts of the <a> tag."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.opening_tag = f'<a href="{base_url}/' # Removed the token from the base url
        self.closing_tag = "</a><br/>"

    def get_link(self, token: str) -> str:
        return f'{self.opening_tag}{token}">{token}{self.closing_tag}'


def generate_labyrinth_page(seed: str, depth: int = 5) -> str:
    rng = random.Random(seed)
    links = []
    for i in range(depth):
        token = hashlib.sha256(f"{seed}-{i}".encode()).hexdigest()[:8]
        links.append(token) # just store the token now
    rng.shuffle(links)
    body = ""

    # Initialize Flyweight
    link_flyweight = LinkFlyweight("/tarpit")

    body = "".join(link_flyweight.get_link(link) for link in links)

    css = generate_obfuscated_css()
    js = generate_obfuscated_js()
    fp = ""
    if os.getenv("ENABLE_FINGERPRINTING", "false").lower() == "true":
        fp = generate_fingerprinting_script()
    return (
        "<html><head><title>Loading...</title>" + css + "</head>"
        "<body>" + body + js + fp + "</body></html>"
    )
