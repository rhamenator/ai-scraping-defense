"""Cloud Dashboard API module."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="Cloud Dashboard API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active WebSocket connections
active_connections: List[WebSocket] = []


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        """Initialize the connection manager."""
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket."""
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        """Send a message to all connected WebSockets."""
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.exception("Error sending message to WebSocket: %s", e)


manager = ConnectionManager()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Cloud Dashboard API"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/stats")
async def get_stats():
    """Get current statistics."""
    # This would typically fetch from a database or cache
    return {
        "total_requests": 1234,
        "blocked_requests": 56,
        "active_sessions": 12,
        "threat_level": "low"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data}")
            
            # Echo back for now
            await manager.send_personal_message(f"Message received: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")


async def send_update(data: Dict[str, Any]):
    """Send an update to all connected WebSocket clients."""
    message = json.dumps(data)
    await manager.broadcast(message)


# Background task to simulate real-time updates
async def simulate_updates():
    """Simulate real-time data updates."""
    import random
    
    while True:
        await asyncio.sleep(5)  # Send update every 5 seconds
        
        update_data = {
            "timestamp": asyncio.get_event_loop().time(),
            "total_requests": random.randint(1000, 2000),
            "blocked_requests": random.randint(50, 100),
            "active_sessions": random.randint(10, 20),
            "threat_level": random.choice(["low", "medium", "high"])
        }
        
        await send_update(update_data)


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("Cloud Dashboard API starting up")
    # Uncomment to enable simulated updates
    # asyncio.create_task(simulate_updates())


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Cloud Dashboard API shutting down")


async def fanout_to_websockets(message: dict):
    """Fan out a message to all connected WebSocket clients."""
    for connection in manager.active_connections[:]:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.exception("WebSocket fanout error: %s", e)
