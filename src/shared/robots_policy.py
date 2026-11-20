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


def _hex_escape(octets: bytes, i: int) -> int | None:
    """Return the byte value of a valid %XX escape starting at i, else None."""
    if octets[i] == 37 and re.fullmatch(rb"[0-9A-Fa-f]{2}", octets[i + 1 : i + 3]):
        return int(octets[i + 1 : i + 3], 16)
    return None


def _needs_escape(byte: int, pattern: bool) -> bool:
    return byte > 127 or byte <= 32 or byte == 36 or (byte == 42 and not pattern)


def _normalize(value: str, *, pattern: bool = False) -> str:
    result = []
    octets = value.encode("utf-8")
    i = 0
    while i < len(octets):
        decoded = _hex_escape(octets, i)
        if decoded is not None:
            char = chr(decoded)
            result.append(
                char if re.fullmatch(r"[A-Za-z0-9._~-]", char) else f"%{decoded:02X}"
            )
            i += 3
            continue
        byte = octets[i]
        result.append(f"%{byte:02X}" if _needs_escape(byte, pattern) else chr(byte))
        i += 1
    return "".join(result)


def _build_rule(key: str, value: str) -> Rule | None:
    if not value.startswith(("/", "*")):
        return None
    anchored = value.endswith("$")
    pattern = _normalize(value[:-1] if anchored else value, pattern=True)
    # RFC 9309: the longest pattern is the most specific. The "$" is part of the
    # pattern, so an anchored rule outranks the same text without the anchor.
    length = len(re.sub(r"%[0-9A-F]{2}", "X", pattern).replace("*", "")) + int(anchored)
    return Rule(pattern, anchored, length, key == "allow")


def _start_group(groups: list[Group], current: Group | None, value: str) -> Group | None:
    value = value.lower()
    if value != "*" and not re.fullmatch(r"[a-z_-]+", value):
        return current
    if current is None or current.has_rules:
        current = Group()
        groups.append(current)
    current.agents.append(value)
    return current


def parse(text: str) -> list[Group]:
    groups: list[Group] = []
    current = None
    for line in text.removeprefix("\ufeff").splitlines():
        key, sep, value = line.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            current = _start_group(groups, current, value)
        elif current is not None and key in {"allow", "disallow"}:
            current.has_rules = True
            rule = _build_rule(key, value)
            if rule is not None:
                current.rules.append(rule)
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


def _agent_selected(agent: str, ua: str) -> bool:
    return agent != "*" and bool(
        re.search(r"(?<![a-z_-])" + re.escape(agent) + r"(?![a-z_-])", ua)
    )


def _select_groups(groups: list[Group], ua: str) -> list[Group]:
    """Groups naming the client win; otherwise the "*" groups apply."""
    specific = [g for g in groups if any(_agent_selected(a, ua) for a in g.agents)]
    wildcard = [g for g in groups if "*" in g.agents]
    return specific or wildcard


def _verdict_allows(groups: list[Group], path: str) -> bool:
    best, allowed = -1, True
    for rule in (r for group in groups for r in group.rules):
        if rule.length >= best and _matches(path, rule):
            allowed = rule.allow if rule.length > best else allowed or rule.allow
            best = rule.length
    return allowed


def is_disallowed(groups: list[Group], path: str, user_agent: str = "") -> bool:
    if not path:
        return False
    path = _normalize(path)
    if path == "/robots.txt" or path.startswith("/robots.txt?"):
        return False
    return not _verdict_allows(_select_groups(groups, (user_agent or "").lower()), path)
