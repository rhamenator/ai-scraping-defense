import asyncio
import os
import logging

from src.util import peer_blocklist_sync

SYNC_INTERVAL_SECONDS = int(os.getenv("PEER_BLOCKLIST_SYNC_INTERVAL", "3600"))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def run_sync_loop(stop_event: asyncio.Event | None = None) -> None:
    """Run the peer blocklist sync task periodically."""
    if stop_event is None:
        stop_event = asyncio.Event()
    while not stop_event.is_set():
        try:
            await peer_blocklist_sync.sync_peer_blocklists()
        except Exception as exc:  # pragma: no cover - unexpected
            logger.error("Peer blocklist sync failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SYNC_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


if __name__ == "__main__":
    try:
        asyncio.run(run_sync_loop())
    except KeyboardInterrupt:
        logger.info("Peer blocklist sync daemon stopped")
