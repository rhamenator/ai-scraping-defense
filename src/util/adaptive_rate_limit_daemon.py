from __future__ import annotations

import asyncio
import json
import logging
import os

import redis.asyncio as redis

from src.util.adaptive_rate_limit_manager import compute_and_update

SYNC_INTERVAL_SECONDS = int(os.getenv("ADAPTIVE_RATE_LIMIT_INTERVAL", "60"))
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
RATE_LIMIT_EVENT_CHANNEL = "rate_limit_events"


logger = logging.getLogger(__name__)


async def get_redis_client():
    """Create and return an async Redis client."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )


async def subscribe_rate_limit_events():
    """Subscribe to rate limit events from Redis Pub/Sub."""
    redis_client = await get_redis_client()
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(RATE_LIMIT_EVENT_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    event_data = json.loads(message["data"])
                    await handle_rate_limit_event(event_data)
                except json.JSONDecodeError as e:
                    logger.error("Failed to decode rate limit event: %s", e)
                except Exception as e:
                    logger.error("Error handling rate limit event: %s", e)
    finally:
        await redis_client.aclose()


async def handle_rate_limit_event(event_data):
    """
    Process the rate limit event.

    This is a placeholder for future event-driven rate limit adjustments.
    Event data is expected to contain rate limit configuration changes
    that should be applied dynamically without daemon restart.

    Args:
        event_data: Dictionary containing rate limit event information
    """
    logger.info("Received rate limit event: %s", event_data)
    # Planned: implement dynamic rate limit updates based on event_data.


async def run_loop(stop_event: asyncio.Event | None = None) -> None:
    """Main loop for adaptive rate limit updates."""
    if stop_event is None:
        stop_event = asyncio.Event()
    while not stop_event.is_set():
        try:
            # Run synchronous compute_and_update in an executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, compute_and_update)
        except Exception as exc:  # pragma: no cover - unexpected
            logger.error("Adaptive rate limit update failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SYNC_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


async def main():
    """Main entry point for the daemon."""
    # Python 3.11+ has TaskGroup with proper exception handling
    if hasattr(asyncio, "TaskGroup"):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(subscribe_rate_limit_events())
            tg.create_task(run_loop())
    else:
        # Fallback for Python 3.10 - both tasks will be cancelled if one fails
        try:
            await asyncio.gather(
                subscribe_rate_limit_events(),
                run_loop(),
            )
        except Exception:
            # Ensure both tasks are cleaned up on error
            raise


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Adaptive rate limit daemon stopped")
