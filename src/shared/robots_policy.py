"""RFC 9309 policy matching; User-Agent group selection never grants identity trust."""

import re
from dataclasses import dataclass, field


@dataclass
class Rule:
    pattern: str
    anchored: bool
    length: int
    allow: bool


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    has_rules: bool = False


def _normalize(value: str, *, pattern: bool = False) -> str:
    result = []
    octets = value.encode("utf-8")
    i = 0
    while i < len(octets):
        byte = octets[i]
        if byte == 37 and re.fullmatch(rb"[0-9A-Fa-f]{2}", octets[i + 1 : i + 3]):
            decoded = int(octets[i + 1 : i + 3], 16)
            char = chr(decoded)
            result.append(
                char if re.fullmatch(r"[A-Za-z0-9._~-]", char) else f"%{decoded:02X}"
            )
            i += 3
        else:
            if byte > 127 or byte <= 32 or byte == 36 or (byte == 42 and not pattern):
                result.append(f"%{byte:02X}")
            else:
                result.append(chr(byte))
            i += 1
    return "".join(result)


def parse(text: str) -> list[Group]:
    groups: list[Group] = []
    current = None
    for line in text.removeprefix("\ufeff").splitlines():
        line = line.split("#", 1)[0]
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            value = value.lower()
            if value == "*" or re.fullmatch(r"[a-z_-]+", value):
                if current is None or current.has_rules:
                    current = Group()
                    groups.append(current)
                current.agents.append(value)
        elif current is not None and key in {"allow", "disallow"}:
            current.has_rules = True
            if value.startswith(("/", "*")):
                anchored = value.endswith("$")
                pattern = _normalize(value[:-1] if anchored else value, pattern=True)
                length = len(re.sub(r"%[0-9A-F]{2}", "X", pattern).replace("*", ""))
                current.rules.append(Rule(pattern, anchored, length, key == "allow"))
    return groups


def _matches(path: str, rule: Rule) -> bool:
    pattern = rule.pattern + ("" if rule.anchored else "*")
    i = j = 0
    star = resume = None
    while i < len(path):
        char = pattern[j : j + 1]
        if char == "*":
            star, resume, j = j, i, j + 1
        elif char and char == path[i]:
            i, j = i + 1, j + 1
        elif star is not None:
            resume += 1
            i, j = resume, star + 1
        else:
            return False
    while pattern[j : j + 1] == "*":
        j += 1
    return j == len(pattern)


def is_disallowed(groups: list[Group], path: str, user_agent: str = "") -> bool:
    if not path:
        return False
    path = _normalize(path)
    if path == "/robots.txt" or path.startswith("/robots.txt?"):
        return False
    ua = (user_agent or "").lower()
    specific, wildcard = [], []
    for group in groups:
        if any(
            agent != "*"
            and re.search(r"(?<![a-z_-])" + re.escape(agent) + r"(?![a-z_-])", ua)
            for agent in group.agents
        ):
            specific.append(group)
        if "*" in group.agents:
            wildcard.append(group)
    best, allowed = -1, True
    for group in specific or wildcard:
        for rule in group.rules:
            if rule.length >= best and _matches(path, rule):
                allowed = rule.allow if rule.length > best else allowed or rule.allow
                best = rule.length
    return not allowed
