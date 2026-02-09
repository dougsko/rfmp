#!/usr/bin/env python3
"""Main entry point for RFMP daemon."""

import asyncio
import signal
import sys
import argparse
from datetime import datetime
from typing import List, Optional
import json
import uvicorn

from .config import Config
from .storage import Database
from .network import DirewolfConnection, DirewolfConfig, AX25Frame
from .protocol import (
    FrameParser,
    Message,
    MSG,
    FRAG,
    SYNC,
    REQ,
    Fragmenter
)
from .sync import RotatingBloomFilter, AdaptiveTiming, RateLimiter
from .api import create_app
from .utils import setup_logging, get_logger


class RFMPDaemon:
    """Main RFMP daemon class."""

    def __init__(self, config: Config):
        """
        Initialize RFMP daemon.

        Args:
            config: Daemon configuration
        """
        self.config = config
        self.logger = get_logger(__name__)
        self.running = False
        self.start_time = datetime.utcnow()

        # Initialize components
        self.database = Database(config.storage.database_path)
        self.fragmenter = Fragmenter(config.protocol.fragment_threshold)

        # Network components
        direwolf_config = DirewolfConfig(
            host=config.network.direwolf_host,
            port=config.network.direwolf_port,
            reconnect_interval=config.network.reconnect_interval,
            offline_mode=config.network.offline_mode,
            callsign=config.node.callsign,
            ssid=config.node.ssid
        )
        self.direwolf = DirewolfConnection(direwolf_config)

        # Sync components
        self.bloom_filter = RotatingBloomFilter(
            window_duration=config.sync.window_duration,
            window_count=config.sync.window_count,
            bloom_bits=config.sync.bloom_bits,
            bloom_hashes=config.sync.bloom_hashes
        )

        self.timing = AdaptiveTiming()
        self.rate_limiter = RateLimiter()

        # API
        self.api_app = create_app(self)
        self.websocket_clients: List = []

        # Background tasks
        self.sync_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self.transmission_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the daemon."""
        self.logger.info("Starting RFMP daemon", version="0.3.0", callsign=self.config.node.callsign)

        # Connect to database
        await self.database.connect()
        self.logger.info("Database connected")

        # Set up Direwolf callbacks
        self.direwolf.on_frame_received = self.handle_received_frame
        self.direwolf.on_connected = self.on_direwolf_connected
        self.direwolf.on_disconnected = self.on_direwolf_disconnected

        # Start Direwolf connection
        await self.direwolf.start()

        # Start background tasks
        self.running = True
        self.sync_task = asyncio.create_task(self.sync_loop())
        self.cleanup_task = asyncio.create_task(self.cleanup_loop())
        self.transmission_task = asyncio.create_task(self.transmission_loop())

        self.logger.info("RFMP daemon started")

    async def stop(self):
        """Stop the daemon."""
        self.logger.info("Stopping RFMP daemon")
        self.running = False

        # Stop background tasks
        if self.sync_task:
            self.sync_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        if self.transmission_task:
            self.transmission_task.cancel()

        # Stop Direwolf connection
        await self.direwolf.stop()

        # Close database
        await self.database.disconnect()

        self.logger.info("RFMP daemon stopped")

    async def handle_received_frame(self, ax25_frame: AX25Frame):
        """
        Handle a received AX.25 frame.

        Args:
            ax25_frame: Received AX.25 frame
        """
        try:
            # Parse RFMP frame
            frame = FrameParser.decode(ax25_frame.info)
            if not frame:
                self.logger.debug("Failed to parse RFMP frame")
                return

            # Handle based on frame type
            if isinstance(frame, MSG):
                await self.handle_msg_frame(frame)
            elif isinstance(frame, FRAG):
                await self.handle_frag_frame(frame)
            elif isinstance(frame, SYNC):
                await self.handle_sync_frame(frame, str(ax25_frame.source))
            elif isinstance(frame, REQ):
                await self.handle_req_frame(frame, str(ax25_frame.source))

        except Exception as e:
            self.logger.error("Error handling frame", error=str(e))

    async def handle_msg_frame(self, frame: MSG):
        """Handle received MSG frame."""
        # Atomically check and mark as seen to avoid race condition
        is_new = await self.database.mark_seen_if_new(frame.id)
        if not is_new:
            self.logger.debug("Duplicate message", id=frame.id)
            return

        # Save to database
        message_data = {
            'id': frame.id,
            'from_node': frame.from_node,
            'timestamp': frame.timestamp,
            'channel': frame.channel,
            'priority': frame.priority,
            'reply_to': frame.reply_to,
            'body': frame.body,
            'raw_frame': str(frame.to_dict())
        }

        is_new = await self.database.save_message(message_data)
        if is_new:
            self.logger.info("New message received",
                             id=frame.id,
                             from_node=frame.from_node,
                             channel=frame.channel)

            # Add to Bloom filter
            self.bloom_filter.add(frame.id)

            # Notify WebSocket clients with serialized client representation
            stored = await self.database.get_message(frame.id)
            client = self.serialize_message_for_client(stored)
            await self.notify_websocket_clients({'type': 'message', 'data': client})

            # Update user stats (track activity by application-level author)
            try:
                await self.database._update_user_stats(stored.get('author'), 'message')
            except Exception:
                pass

            # Consider rebroadcasting
            if not await self.database.is_seen(frame.id, rebroadcast=True):
                # Schedule rebroadcast with delay
                delay = self.timing.calculate_rebroadcast_delay(frame.priority)
                await self.database.queue_transmission(
                    frame_type='MSG',
                    frame_data=json.dumps(frame.to_dict()),
                    priority=frame.priority,
                    delay_seconds=delay
                )
                await self.database.mark_seen(frame.id, rebroadcast=True)

    async def handle_frag_frame(self, frame: FRAG):
        """Handle received FRAG frame."""
        # Check if we've seen this fragment
        if await self.database.is_seen(frame.message_id, fragment_idx=frame.idx):
            self.logger.debug("Duplicate fragment", id=frame.message_id, idx=frame.idx)
            return

        # Mark as seen
        await self.database.mark_seen(frame.message_id, fragment_idx=frame.idx)

        # Save fragment
        fragment_data = {
            'message_id': frame.message_id,
            'idx': frame.idx,
            'total': frame.total,
            'data': frame.data
        }
        await self.database.save_fragment(fragment_data)

        # Try to reassemble
        is_new, complete_msg = self.fragmenter.add_fragment(frame)
        if complete_msg:
            # Handle complete message
            await self.handle_msg_frame(complete_msg)

    async def handle_sync_frame(self, frame: SYNC, from_node: str):
        """Handle received SYNC frame."""
        self.logger.debug("SYNC received", from_node=from_node)

        # Update node stats
        await self.database._update_node_stats(from_node, 'sync')

        # Compare Bloom filters to find missing messages
        # This would require comparing with our local messages
        # For now, just log it
        self.logger.info("SYNC frame received", from_node=from_node, window=frame.window_index)

    async def handle_req_frame(self, frame: REQ, from_node: str):
        """Handle received REQ frame."""
        self.logger.debug("REQ received", from_node=from_node, message_id=frame.message_id)

        # Update node stats
        await self.database._update_node_stats(from_node, 'req')

        # Check if we have the requested message
        message = await self.database.get_message(frame.message_id)

        if message:
            # We have it - schedule transmission
            msg_frame = MSG(
                id=message['id'],
                from_node=message['from_node'],
                timestamp=message['timestamp'],
                channel=message['channel'],
                priority=message['priority'],
                reply_to=message.get('reply_to'),
                body=message['body']
            )

            # Check if it needs fragmentation
            fragments = self.fragmenter.fragment_message(msg_frame)

            if fragments:
                # Send fragments
                for i, frag in enumerate(fragments):
                    delay = self.timing.calculate_fragment_delay(i, len(fragments))
                    await self.database.queue_transmission(
                        frame_type='FRAG',
                        frame_data=json.dumps(frag.to_dict()),
                        priority=message['priority'],
                        delay_seconds=delay
                    )
            else:
                # Send complete message
                delay = self.timing.calculate_delay(message['priority'])
                await self.database.queue_transmission(
                    frame_type='MSG',
                    frame_data=json.dumps(msg_frame.to_dict()),
                    priority=message['priority'],
                    delay_seconds=delay
                )

    async def send_message(self, channel: str, body: str, priority: int = 1,
                           reply_to: Optional[str] = None,
                           author: Optional[str] = None) -> Message:
        """
        Send a new message.

        Args:
            channel: Channel to send on
            body: Message body
            priority: Message priority
            reply_to: Optional message being replied to
        """

        # Determine node callsign used for ID generation and internal tracking
        from_node = f"{self.config.node.callsign}"
        if self.config.node.ssid > 0:
            from_node += f"-{self.config.node.ssid}"

        # Create the high-level Message object (IDs incorporate `author` when provided)
        message = Message.create(
            from_node=from_node,
            channel=channel,
            body=body,
            priority=priority,
            reply_to=reply_to,
            author=author
        )

        # Build frame dict and, if an application `author` was provided, use it
        # as the RFMP payload `from` while keeping the message ID and internal
        # `from_node` tied to the daemon's configured callsign. This allows
        # multiple users to share the same physical node while advertising a
        # session nickname in the RFMP payload.
        msg_frame = message.to_frame()
        frame_dict = msg_frame.to_dict()
        if author:
            # Use the transient session nickname as the payload `from`
            frame_dict['from'] = author

        # Store the payload representation in the DB so raw_frame reflects what
        # will actually be transmitted on-air (payload may show nickname).
        message_data = {
            'id': message.id,
            'from_node': message.from_node,
            'author': author,
            'timestamp': message.timestamp,
            'channel': message.channel,
            'priority': message.priority,
            'reply_to': message.reply_to,
            'body': message.body,
            'raw_frame': json.dumps(frame_dict)
        }

        # Save to database
        await self.database.save_message(message_data)

        # Add to Bloom filter (still keyed by message.id)
        self.bloom_filter.add(message.id)

        # Recreate a MSG frame object from the possibly-modified frame_dict so
        # fragmentation and transmission use the payload `from` value.
        from .protocol.frames import MSG as MSGFrame
        msg_frame = MSGFrame.from_dict(frame_dict)

        # Check if it needs fragmentation
        fragments = self.fragmenter.fragment_message(msg_frame)

        if fragments:
            # Queue fragments
            for i, frag in enumerate(fragments):
                delay = self.timing.calculate_fragment_delay(i, len(fragments))
                await self.database.queue_transmission(
                    frame_type='FRAG',
                    frame_data=json.dumps(frag.to_dict()),
                    priority=priority,
                    delay_seconds=delay
                )
        else:
            # Queue complete message (use the modified frame dict)
            delay = self.timing.calculate_delay(priority)
            await self.database.queue_transmission(
                frame_type='MSG',
                frame_data=json.dumps(frame_dict),
                priority=priority,
                delay_seconds=delay
            )

        self.logger.info("Message queued for transmission", id=message.id, channel=channel)

        # Notify websocket clients immediately so UIs reflect the display name
        try:
            stored = await self.database.get_message(message.id)
            client = self.serialize_message_for_client(stored)
            await self.notify_websocket_clients({'type': 'message', 'data': client})
        except Exception as e:
            self.logger.error("Failed to broadcast message to WebSocket clients", error=str(e), message_id=message.id)

        return message

    async def sync_loop(self):
        """Periodic SYNC frame transmission."""
        while self.running:
            try:
                # Wait for sync interval
                await asyncio.sleep(self.config.sync.sync_interval)

                # Create SYNC frame
                from_node = f"{self.config.node.callsign}"
                if self.config.node.ssid > 0:
                    from_node += f"-{self.config.node.ssid}"

                sync_frame = SYNC(
                    from_node=from_node,
                    bloom_filters=self.bloom_filter.get_filters(),
                    window_index=self.bloom_filter.get_current_window_index()
                )

                # Queue for transmission
                delay = self.timing.calculate_sync_delay()
                await self.database.queue_transmission(
                    frame_type='SYNC',
                    frame_data=json.dumps(sync_frame.to_dict()),
                    priority=2,  # Medium priority
                    delay_seconds=delay
                )

                self.logger.debug("SYNC frame queued")

            except Exception as e:
                self.logger.error("Error in sync loop", error=str(e))

    async def cleanup_loop(self):
        """Periodic cleanup tasks."""
        while self.running:
            try:
                # Wait for cleanup interval
                await asyncio.sleep(300)  # 5 minutes

                # Clean up old fragments
                await self.database.cleanup_old_fragments()

                # Clean up seen cache
                await self.database.cleanup_seen_cache()

                # Clean up fragment collectors
                expired = self.fragmenter.cleanup_expired()
                if expired:
                    self.logger.debug("Cleaned up fragment collectors", count=len(expired))

                # Clean up rate limiter
                self.rate_limiter.cleanup_old_records()

            except Exception as e:
                self.logger.error("Error in cleanup loop", error=str(e))

    async def transmission_loop(self):
        """Process transmission queue."""
        while self.running:
            try:
                # Get next frame to transmit
                item = await self.database.get_next_transmission()

                if item:
                    # Parse frame data
                    frame_data = json.loads(item['frame_data'])

                    # Create appropriate frame
                    if item['frame_type'] == 'MSG':
                        frame = MSG.from_dict(frame_data)
                    elif item['frame_type'] == 'FRAG':
                        frame = FRAG.from_dict(frame_data)
                    elif item['frame_type'] == 'SYNC':
                        frame = SYNC.from_dict(frame_data)
                    elif item['frame_type'] == 'REQ':
                        frame = REQ.from_dict(frame_data)
                    else:
                        continue

                    # Encode and send
                    encoded = FrameParser.encode(frame)
                    await self.direwolf.send_frame(encoded)

                    self.logger.debug("Frame transmitted", type=item['frame_type'])

                else:
                    # No frames to send, wait a bit
                    await asyncio.sleep(0.1)

            except Exception as e:
                self.logger.error("Error in transmission loop", error=str(e))
                await asyncio.sleep(1)

    async def on_direwolf_connected(self):
        """Callback when Direwolf connects."""
        self.logger.info("Connected to Direwolf")

    async def on_direwolf_disconnected(self):
        """Callback when Direwolf disconnects."""
        self.logger.warning("Disconnected from Direwolf")

    async def notify_websocket_clients(self, data: dict):
        """Notify WebSocket clients of an event."""
        message = json.dumps(data)
        disconnected = []

        self.logger.info("Broadcasting to WebSocket clients", client_count=len(self.websocket_clients))

        for i, client in enumerate(self.websocket_clients):
            try:
                self.logger.debug(f"Sending to client {i+1}/{len(self.websocket_clients)}")
                await client.send_text(message)
                self.logger.debug(f"Successfully sent to client {i+1}")
            except Exception as e:
                self.logger.info(f"WebSocket client {i+1} disconnected during broadcast: {type(e).__name__}: {e}")
                disconnected.append(client)

        # Remove disconnected clients (check first to avoid race condition)
        for client in disconnected:
            if client in self.websocket_clients:
                self.websocket_clients.remove(client)

        if disconnected:
            self.logger.debug("Removed disconnected WebSocket clients", count=len(disconnected))

    async def get_stats(self) -> dict:
        """Get daemon statistics."""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()

        # Get database stats
        recent_messages = await self.database.get_recent_messages(limit=1000)
        active_nodes = await self.database.get_active_nodes(since_seconds=3600)

        return {
            'uptime_seconds': uptime,
            'message_count': len(recent_messages),
            'active_nodes': len(active_nodes),
            'bloom_filter': self.bloom_filter.get_stats(),
            'timing': self.timing.get_stats(),
            'rate_limiter': self.rate_limiter.get_stats()
        }

    def serialize_message_for_client(self, stored: dict) -> dict:
        """Serialize a stored DB message row into the API/WS payload.

        This creates a compact dict used consistently by REST responses and
        websocket broadcasts. It prefers the stored `author` as the
        application-level display name.
        """
        if not stored:
            return {}

        client = {
            'id': stored['id'],
            'from_node': stored.get('from_node'),
            'author': stored.get('author'),
            'timestamp': stored.get('timestamp'),
            'channel': stored.get('channel'),
            'priority': stored.get('priority'),
            'reply_to': stored.get('reply_to'),
            'body': stored.get('body'),
            'received_at': datetime.fromtimestamp(stored['received_at']).isoformat() if stored.get('received_at') else None,
            'transmitted_at': datetime.fromtimestamp(stored['transmitted_at']).isoformat() if stored.get('transmitted_at') else None
        }

        return client


async def run_daemon(config: Config):
    """Run the RFMP daemon."""
    # Create daemon
    daemon = RFMPDaemon(config)
    # Start daemon
    await daemon.start()

    # Start API server
    api_config = uvicorn.Config(
        daemon.api_app,
        host=config.api.host,
        port=config.api.port,
        log_level=config.logging.level.lower()
    )
    server = uvicorn.Server(api_config)

    # Run Uvicorn in background and monitor its shutdown flag. When the API
    # server requests exit (e.g. on SIGINT/SIGTERM), stop the RFMP daemon so
    # the process can terminate cleanly.
    server_task = asyncio.create_task(server.serve())

    try:
        while daemon.running and not getattr(server, "should_exit", False):
            await asyncio.sleep(1)
    finally:
        if daemon.running:
            await daemon.stop()

        # Ensure the server finishes shutdown
        await server_task


async def daemon_loop(daemon: RFMPDaemon):
    """Keep daemon running."""
    while daemon.running:
        await asyncio.sleep(1)


def main():
    """Main entry point."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="RFMP Daemon")
    parser.add_argument(
        '-c', '--config',
        help='Configuration file path',
        default=None
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Load configuration
    config = Config.load_from_file(args.config)

    # Override log level if verbose
    if args.verbose:
        config.logging.level = "DEBUG"

    # Set up logging
    setup_logging(
        log_level=config.logging.level,
        log_file=config.logging.file,
        max_size=config.logging.max_size,
        backup_count=config.logging.backup_count
    )

    # Run daemon
    asyncio.run(run_daemon(config))


if __name__ == "__main__":
    main()