import asyncio
import logging
import os

from src.util.adaptive_rate_limit_manager import compute_and_update

SYNC_INTERVAL_SECONDS = int(os.getenv("ADAPTIVE_RATE_LIMIT_INTERVAL", "60"))

logger = logging.getLogger(__name__)


async def run_loop(stop_event: asyncio.Event | None = None) -> None:
    if stop_event is None:
        stop_event = asyncio.Event()
    while not stop_event.is_set():
        try:
            compute_and_update()
        except Exception as exc:  # pragma: no cover - unexpected
            logger.error("Adaptive rate limit update failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SYNC_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    try:
        asyncio.run(run_loop())
    except KeyboardInterrupt:
        logger.info("Adaptive rate limit daemon stopped")
