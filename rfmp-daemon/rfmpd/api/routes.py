"""REST API routes for RFMP daemon."""

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
import asyncio
import json

from .schemas import (
    MessageRequest,
    MessageResponse,
    NodeResponse,
    ChannelResponse,
    StatusResponse,
    ErrorResponse,
    CallsignRequest
)


def create_app(daemon) -> FastAPI:
    """
    Create FastAPI application.

    Args:
        daemon: RFMP daemon instance

    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="RFMP Daemon API",
        description="RF Microblog Protocol Daemon REST API",
        version="v1"
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=daemon.config.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store daemon reference
    app.state.daemon = daemon

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    # Message endpoints
    @app.post("/messages", response_model=MessageResponse)
    async def send_message(request: MessageRequest):
        """Send a new message."""
        try:
            # Create message (author is optional, provided by web UI session)
            message = await daemon.send_message(
                channel=request.channel,
                body=request.body,
                priority=request.priority,
                reply_to=request.reply_to,
                author=request.author
            )

            # Retrieve stored message (includes optional author) and serialize
            stored = await daemon.database.get_message(message.id)
            client = daemon.serialize_message_for_client(stored)

            return MessageResponse(**client)

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/messages", response_model=List[MessageResponse])
    async def get_messages(
        channel: Optional[str] = Query(None, description="Filter by channel"),
        from_node: Optional[str] = Query(None, description="Filter by sender"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum messages to return")
    ):
        """Get recent messages."""
        try:
            messages = await daemon.database.get_recent_messages(
                limit=limit,
                channel=channel,
                from_node=from_node
            )

            return [MessageResponse(**daemon.serialize_message_for_client(msg)) for msg in messages]

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/messages/{message_id}", response_model=MessageResponse)
    async def get_message(message_id: str):
        """Get a specific message by ID."""
        try:
            message = await daemon.database.get_message(message_id)

            if not message:
                raise HTTPException(status_code=404, detail="Message not found")

            return MessageResponse(**daemon.serialize_message_for_client(message))

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Node endpoints
    @app.get("/nodes", response_model=List[NodeResponse])
    async def get_nodes(
        active_hours: int = Query(24, ge=1, description="Show nodes active in last N hours")
    ):
        """Get list of seen nodes."""
        try:
            nodes = await daemon.database.get_active_nodes(since_seconds=active_hours * 3600)

            return [
                NodeResponse(
                    callsign=node['callsign'],
                    first_seen=datetime.fromtimestamp(node['first_seen']),
                    last_seen=datetime.fromtimestamp(node['last_seen']),
                    last_sync=datetime.fromtimestamp(node['last_sync']) if node.get('last_sync') else None,
                    message_count=node.get('message_count', 0),
                    sync_count=node.get('sync_count', 0),
                    req_count=node.get('req_count', 0)
                )
                for node in nodes
            ]

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Channel endpoints
    @app.get("/channels", response_model=List[ChannelResponse])
    async def get_channels():
        """Get list of known channels."""
        try:
            channels = await daemon.database.get_channels()

            return [
                ChannelResponse(
                    name=chan['name'],
                    first_message=datetime.fromtimestamp(chan['first_message']),
                    last_message=datetime.fromtimestamp(chan['last_message']),
                    message_count=chan.get('message_count', 0),
                    unique_nodes=chan.get('unique_nodes', 0)
                )
                for chan in channels
            ]

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Status endpoint
    @app.get("/status", response_model=StatusResponse)
    async def get_status():
        """Get daemon status and statistics."""
        try:
            stats = await daemon.get_stats()

            return StatusResponse(
                version="0.3.0",
                uptime_seconds=stats['uptime_seconds'],
                connected_to_direwolf=daemon.direwolf.is_connected(),
                node_callsign=f"{daemon.config.node.callsign}-{daemon.config.node.ssid}" if daemon.config.node.ssid > 0 else daemon.config.node.callsign,
                stats=stats
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Configuration endpoints
    @app.post("/config/callsign")
    async def update_callsign(request: CallsignRequest):
        """Update the node callsign and SSID."""
        try:
            # Update config
            daemon.config.node.callsign = request.callsign
            daemon.config.node.ssid = request.ssid

            # Update direwolf connection config
            daemon.direwolf.config.callsign = request.callsign
            daemon.direwolf.config.ssid = request.ssid

            return {
                "success": True,
                "callsign": request.callsign,
                "ssid": request.ssid,
                "full_callsign": f"{request.callsign}-{request.ssid}" if request.ssid > 0 else request.callsign
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/config/callsign")
    async def get_callsign():
        """Get the current node callsign."""
        return {
            "callsign": daemon.config.node.callsign,
            "ssid": daemon.config.node.ssid,
            "full_callsign": f"{daemon.config.node.callsign}-{daemon.config.node.ssid}" if daemon.config.node.ssid > 0 else daemon.config.node.callsign
        }

    # WebSocket endpoint for real-time updates
    @app.websocket("/stream")
    async def websocket_stream(websocket: WebSocket):
        """WebSocket endpoint for real-time message updates."""
        await websocket.accept()

        # Add websocket to daemon's connected clients
        daemon.websocket_clients.append(websocket)
        daemon.logger.info("WebSocket client connected", client_count=len(daemon.websocket_clients))

        try:
            # Just wait for messages - no timeouts, no ping/pong
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            daemon.logger.info("WebSocket client disconnected")
        except Exception as e:
            daemon.logger.error("WebSocket client error", error=str(e))
        finally:
            if websocket in daemon.websocket_clients:
                daemon.websocket_clients.remove(websocket)
                daemon.logger.info("Removed WebSocket client", remaining=len(daemon.websocket_clients))

    return app