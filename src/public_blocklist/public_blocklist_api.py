import fcntl
import json
import os
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, IPvAnyAddress

PUBLIC_BLOCKLIST_FILE = os.getenv(
    "PUBLIC_BLOCKLIST_FILE", "./data/public_blocklist.json"
)
PUBLIC_BLOCKLIST_API_KEY = os.getenv("PUBLIC_BLOCKLIST_API_KEY")
if not PUBLIC_BLOCKLIST_API_KEY:
    raise RuntimeError("PUBLIC_BLOCKLIST_API_KEY environment variable is required")

app = FastAPI()


def _load_blocklist() -> List[str]:
    if os.path.exists(PUBLIC_BLOCKLIST_FILE):
        try:
            with open(PUBLIC_BLOCKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [ip for ip in data if isinstance(ip, str)]
                if isinstance(data, dict) and isinstance(data.get("ips"), list):
                    return [ip for ip in data["ips"] if isinstance(ip, str)]
        except Exception:
            pass
    return []


def _save_blocklist(ips: List[str]) -> None:
    os.makedirs(os.path.dirname(PUBLIC_BLOCKLIST_FILE), exist_ok=True)
    with open(PUBLIC_BLOCKLIST_FILE, "w", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
    try:
        # Try to open the file in r+ mode (read/write, does not truncate)
        f = open(PUBLIC_BLOCKLIST_FILE, "r+", encoding="utf-8")
    except FileNotFoundError:
        # If the file does not exist, create it with w+ mode
        f = open(PUBLIC_BLOCKLIST_FILE, "w+", encoding="utf-8")
    with f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            f.truncate()
            json.dump({"ips": ips}, f)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


BLOCKLIST_IPS = set(_load_blocklist())


class IPReport(BaseModel):
    ip: IPvAnyAddress


@app.get("/list")
def get_list() -> dict:
    """Return the list of known malicious IPs."""
    return {"ips": sorted(BLOCKLIST_IPS)}


@app.post("/report")
def report_ip(report: IPReport, x_api_key: Optional[str] = Header(None)) -> dict:
    """Add an IP address to the public blocklist."""
    if not x_api_key or x_api_key != PUBLIC_BLOCKLIST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    BLOCKLIST_IPS.add(str(report.ip))
    _save_blocklist(sorted(BLOCKLIST_IPS))
    return {"status": "added", "ip": str(report.ip)}


@app.get("/health")
def health() -> dict:
    """Simple health check."""
    return {"status": "ok", "count": len(BLOCKLIST_IPS)}
