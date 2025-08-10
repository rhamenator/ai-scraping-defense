#!/usr/bin/env python3
"""Simple log monitor that submits high-frequency IPs to the escalation engine."""

import argparse
import asyncio
import datetime
import os
import re
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

from src.util.ddos_protection import report_attack

LOG_PATTERN = re.compile(
    r"(?P<ip>\S+) - - \[(?P<time>[^\]]+)\] \"(?P<method>\S+) (?P<path>\S+)"
    r"[^\"]*\" (?P<status>\d+) (?P<bytes>\d+) \"(?P<referer>[^\"]*)\" \"(?P<ua>[^\"]*)\""
)


class RateTracker:
    def __init__(self, threshold: int = 100, window: int = 60) -> None:
        self.threshold = threshold
        self.window = window
        self.events: Dict[str, Deque[float]] = defaultdict(deque)

    def add(self, ip: str) -> int:
        now = asyncio.get_event_loop().time()
        dq = self.events[ip]
        dq.append(now)
        while dq and now - dq[0] > self.window:
            dq.popleft()
        return len(dq)


class GlobalAttackDetector:
    def __init__(
        self,
        total_threshold: int = 1000,
        unique_threshold: int = 200,
        window: int = 60,
    ) -> None:
        self.total_threshold = total_threshold
        self.unique_threshold = unique_threshold
        self.window = window
        self.events: Deque[Tuple[float, str, str, str]] = deque()
        self.ip_counts: Dict[str, int] = defaultdict(int)
        self.ua_counts: Dict[str, int] = defaultdict(int)
        self.path_counts: Dict[str, int] = defaultdict(int)

    def add(self, ip: str, path: str, ua: str) -> Tuple[bool, List[str], str]:
        now = asyncio.get_event_loop().time()
        self.events.append((now, ip, path, ua))
        self.ip_counts[ip] += 1
        self.ua_counts[ua] += 1
        self.path_counts[path] += 1
        while self.events and now - self.events[0][0] > self.window:
            t, old_ip, old_path, old_ua = self.events.popleft()
            self.ip_counts[old_ip] -= 1
            if self.ip_counts[old_ip] <= 0:
                del self.ip_counts[old_ip]
            self.ua_counts[old_ua] -= 1
            if self.ua_counts[old_ua] <= 0:
                del self.ua_counts[old_ua]
            self.path_counts[old_path] -= 1
            if self.path_counts[old_path] <= 0:
                del self.path_counts[old_path]

        total = len(self.events)
        unique_ips = len(self.ip_counts)
        if total >= self.total_threshold and unique_ips >= self.unique_threshold:
            top_ua_count = max(self.ua_counts.values()) if self.ua_counts else 0
            top_path_count = max(self.path_counts.values()) if self.path_counts else 0
            dominant_ratio = max(top_ua_count, top_path_count) / float(total)
            if dominant_ratio > 0.8:
                return True, list(self.ip_counts.keys()), "http_flood"
            return True, list(self.ip_counts.keys()), "volumetric"
        return False, [], ""


async def tail_file(path: str):
    with open(path, "r") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            if not line:
                await asyncio.sleep(0.5)
                continue
            yield line.rstrip()


async def monitor(
    path: str,
    threshold: int,
    window: int,
    global_total: int,
    unique_ips: int,
    report_ttl: int,
) -> None:
    tracker = RateTracker(threshold, window)
    detector = GlobalAttackDetector(global_total, unique_ips, window)
    reported: Dict[str, float] = {}
    async for line in tail_file(path):
        m = LOG_PATTERN.match(line)
        if not m:
            continue
        ip = m.group("ip")
        ua = m.group("ua")
        method = m.group("method")
        req_path = m.group("path")
        count = tracker.add(ip)
        global_hit, ips, global_type = detector.add(ip, req_path, ua)
        now = asyncio.get_event_loop().time()
        # prune reported cache
        for old_ip, ts in list(reported.items()):
            if now - ts > report_ttl:
                del reported[old_ip]

        def maybe_report(target_ip: str, source: str, atype: str) -> None:
            if target_ip not in reported:
                metadata = {
                    "timestamp": datetime.datetime.now(datetime.UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "ip": target_ip,
                    "user_agent": ua,
                    "path": req_path,
                    "method": method,
                    "source": source,
                    "attack_type": atype,
                }
                asyncio.create_task(report_attack(target_ip, metadata, atype))
                reported[target_ip] = now

        if count == threshold:
            maybe_report(ip, "ddos_guard", "rate_limit")

        if global_hit:
            for suspect in ips:
                maybe_report(suspect, "ddos_guard_global", global_type)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local DDoS guard")
    parser.add_argument("--log", default="/var/log/nginx/access.log")
    parser.add_argument("--threshold", type=int, default=100)
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--global-total", type=int, default=1000)
    parser.add_argument("--unique-ips", type=int, default=200)
    parser.add_argument("--report-ttl", type=int, default=300)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await monitor(
        args.log,
        args.threshold,
        args.window,
        args.global_total,
        args.unique_ips,
        args.report_ttl,
    )


if __name__ == "__main__":
    asyncio.run(main())
