import os
from typing import Dict

from fastapi import FastAPI, Header, HTTPException

from src.shared.config import CONFIG
from src.shared.metrics import get_metrics

app = FastAPI()


def _parse_prometheus_metrics(text: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name, value = parts[0], parts[-1]
        try:
            metrics[name] = float(value)
        except ValueError:
            continue
    return metrics


def _generate_recommendations(metrics: Dict[str, float]) -> Dict[str, int]:
    total_requests = sum(
        v for k, v in metrics.items() if k.startswith("http_requests_total")
    )
    tarpit_hits = metrics.get("tarpit_entries_total", 0)
    bots_detected = sum(v for k, v in metrics.items() if k.startswith("bots_detected"))

    recs: Dict[str, int] = {}

    if total_requests:
        tarpit_ratio = tarpit_hits / total_requests
        if tarpit_ratio > 0.05:
            recs["TAR_PIT_MAX_HOPS"] = max(CONFIG.TAR_PIT_MAX_HOPS - 50, 50)
        elif tarpit_ratio < 0.01:
            recs["TAR_PIT_MAX_HOPS"] = CONFIG.TAR_PIT_MAX_HOPS + 50

    if bots_detected > 100:
        recs["BLOCKLIST_TTL_SECONDS"] = min(
            CONFIG.BLOCKLIST_TTL_SECONDS + 43200, 604800
        )
    elif bots_detected < 10:
        recs["BLOCKLIST_TTL_SECONDS"] = max(CONFIG.BLOCKLIST_TTL_SECONDS - 3600, 3600)

    return recs


@app.get("/recommendations")
async def recommendations(
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> Dict[str, Dict[str, int]]:
    expected = os.getenv("RECOMMENDER_API_KEY")
    if not expected or not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
    raw = get_metrics()
    if isinstance(raw, bytes):
        raw = raw.decode()
    metrics = _parse_prometheus_metrics(raw)
    recs = _generate_recommendations(metrics)
    return {"recommendations": recs}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.config_recommender.recommender_api:app",
        host=os.getenv("RECOMMENDER_HOST", "127.0.0.1"),
        port=8010,
    )
