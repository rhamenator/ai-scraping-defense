import fcntl
import json
import logging
import os
from typing import List, Optional

from fastapi import Header, HTTPException
from pydantic import BaseModel, IPvAnyAddress

from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    register_health_check,
)

logger = logging.getLogger(__name__)

PUBLIC_BLOCKLIST_FILE = os.getenv(
    "PUBLIC_BLOCKLIST_FILE", "./data/public_blocklist.json"
)
PUBLIC_BLOCKLIST_API_KEY = os.getenv("PUBLIC_BLOCKLIST_API_KEY")

app = create_app()


@register_health_check(app, "blocklist_store", critical=True)
async def _blocklist_health() -> HealthCheckResult:
    if not os.path.exists(PUBLIC_BLOCKLIST_FILE):
        return HealthCheckResult.degraded({"missing_file": PUBLIC_BLOCKLIST_FILE})
    try:
        ips = _load_blocklist()
    except Exception as exc:  # pragma: no cover - file IO
        return HealthCheckResult.unhealthy({"error": str(exc)})
    return HealthCheckResult.healthy({"entries": len(ips)})


def _load_blocklist() -> List[str]:
    if os.path.exists(PUBLIC_BLOCKLIST_FILE):
        try:
            with open(PUBLIC_BLOCKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [ip for ip in data if isinstance(ip, str)]
                if isinstance(data, dict) and isinstance(data.get("ips"), list):
                    return [ip for ip in data["ips"] if isinstance(ip, str)]
        except FileNotFoundError:  # pragma: no cover - logging side effect
            logger.exception(
                "Public blocklist file not found: %s", PUBLIC_BLOCKLIST_FILE
            )
        except PermissionError:  # pragma: no cover - logging side effect
            logger.exception(
                "Permission denied reading public blocklist file: %s",
                PUBLIC_BLOCKLIST_FILE,
            )
        except json.JSONDecodeError:  # pragma: no cover - logging side effect
            logger.exception(
                "Invalid JSON in public blocklist file: %s", PUBLIC_BLOCKLIST_FILE
            )
        except OSError:  # pragma: no cover - logging side effect
            logger.exception(
                "Failed to load public blocklist from %s", PUBLIC_BLOCKLIST_FILE
            )
    return []


def _save_blocklist(ips: List[str]) -> None:
    os.makedirs(os.path.dirname(PUBLIC_BLOCKLIST_FILE), exist_ok=True)
    with open(PUBLIC_BLOCKLIST_FILE, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        json.dump({"ips": ips}, f)
        f.flush()
        os.fsync(f.fileno())


BLOCKLIST_IPS = set(_load_blocklist())


class IPReport(BaseModel):
    ip: IPvAnyAddress


@app.get("/list")
def get_list() -> dict:
    """Return the list of known malicious IPs."""
    return {"ips": sorted(BLOCKLIST_IPS)}


@app.post("/report")
def report_ip(report: IPReport, x_api_key: Optional[str] = Header(None)) -> dict:
    """Add an IP address to the public blocklist.

    Returns HTTP 503 if the API key is not configured.
    """
    if not PUBLIC_BLOCKLIST_API_KEY:
        raise HTTPException(status_code=503, detail="Service misconfigured")
    if not x_api_key or x_api_key != PUBLIC_BLOCKLIST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    BLOCKLIST_IPS.add(str(report.ip))
    _save_blocklist(sorted(BLOCKLIST_IPS))
    return {"status": "added", "ip": str(report.ip)}
