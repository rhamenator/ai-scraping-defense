import asyncio
import logging
import os

from src.util import community_blocklist_sync

SYNC_INTERVAL_SECONDS = int(os.getenv("COMMUNITY_BLOCKLIST_SYNC_INTERVAL", "3600"))

logger = logging.getLogger(__name__)


async def run_sync_loop(stop_event: asyncio.Event | None = None) -> None:
    """Run the community blocklist sync task periodically."""
    if stop_event is None:
        stop_event = asyncio.Event()
    while not stop_event.is_set():
        try:
            await community_blocklist_sync.sync_blocklist()
        except Exception as e:  # pragma: no cover - unexpected error
            logger.error(f"Blocklist sync failed: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SYNC_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    try:
        asyncio.run(run_sync_loop())
    except KeyboardInterrupt:
        logger.info("Blocklist sync daemon stopped")
