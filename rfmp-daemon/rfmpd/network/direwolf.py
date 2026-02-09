"""Direwolf TCP KISS connection manager."""

import asyncio
import logging
from typing import Optional, Callable, List
from dataclasses import dataclass

from .kiss import KISSProtocol, KISSFrame
from .ax25 import AX25Frame


logger = logging.getLogger(__name__)


@dataclass
class DirewolfConfig:
    """Direwolf connection configuration."""
    host: str = "127.0.0.1"
    port: int = 8001
    reconnect_interval: int = 5
    offline_mode: bool = False
    callsign: str = "N0CALL"
    ssid: int = 0


class DirewolfConnection:
    """Manages TCP connection to Direwolf KISS server."""

    def __init__(self, config: DirewolfConfig):
        """
        Initialize Direwolf connection.

        Args:
            config: Connection configuration
        """
        self.config = config
        self.kiss_protocol = KISSProtocol(port=0)

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        self.connected = False
        self.running = False
        self.receive_task: Optional[asyncio.Task] = None
        self.reconnect_task: Optional[asyncio.Task] = None

        # Callbacks
        self.on_frame_received: Optional[Callable[[AX25Frame], None]] = None
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None

    async def start(self):
        """Start the connection manager."""
        if self.running:
            return

        self.running = True

        if self.config.offline_mode:
            logger.info("Running in offline mode - no Direwolf connection")
            return

        # Start connection task
        self.reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def stop(self):
        """Stop the connection manager."""
        self.running = False

        # Cancel tasks
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass

        if self.reconnect_task:
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass

        # Close connection
        await self._disconnect()

    async def _reconnect_loop(self):
        """Handle automatic reconnection to Direwolf."""
        while self.running:
            if not self.connected:
                try:
                    await self._connect()
                except Exception as e:
                    logger.error(f"Failed to connect to Direwolf at {self.config.host}:{self.config.port}: {e}")
                    logger.info(f"Retrying in {self.config.reconnect_interval} seconds...")
                    await asyncio.sleep(self.config.reconnect_interval)
                    continue

            # Wait before checking again
            await asyncio.sleep(1)

    async def _connect(self):
        """Establish connection to Direwolf."""
        logger.info(f"Connecting to Direwolf at {self.config.host}:{self.config.port}")

        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.config.host,
                self.config.port
            )

            self.connected = True
            logger.info("Connected to Direwolf")

            # Start receive task
            if self.receive_task:
                self.receive_task.cancel()
            self.receive_task = asyncio.create_task(self._receive_loop())

            # Call connected callback
            if self.on_connected:
                asyncio.create_task(self.on_connected())

        except Exception as e:
            self.connected = False
            raise e

    async def _disconnect(self):
        """Disconnect from Direwolf."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass

        self.reader = None
        self.writer = None
        self.connected = False

        # Call disconnected callback
        if self.on_disconnected:
            asyncio.create_task(self.on_disconnected())

        logger.info("Disconnected from Direwolf")

    async def _receive_loop(self):
        """Receive and process frames from Direwolf."""
        buffer = bytearray()

        try:
            while self.connected and self.reader:
                # Read data from socket
                try:
                    data = await self.reader.read(1024)
                except Exception as e:
                    logger.error(f"Error reading from Direwolf: {e}")
                    self.connected = False
                    break

                if not data:
                    # Connection closed
                    logger.warning("Direwolf connection closed")
                    self.connected = False
                    break

                # Add to buffer and process KISS frames
                buffer.extend(data)

                # Process complete KISS frames
                frames = self.kiss_protocol.decode_frames(bytes(buffer))
                buffer = self.kiss_protocol.buffer  # Get remaining buffer

                for kiss_frame in frames:
                    # Decode AX.25 frame
                    ax25_frame = AX25Frame.decode(kiss_frame.data)
                    if ax25_frame:
                        # Check if it's a UI frame for RFMP
                        if ax25_frame.control == 0x03 and ax25_frame.pid == 0xF0:
                            # Call frame received callback
                            if self.on_frame_received:
                                asyncio.create_task(self.on_frame_received(ax25_frame))
                    else:
                        logger.debug("Failed to decode AX.25 frame")

        except asyncio.CancelledError:
            # Task cancelled, clean shutdown
            pass
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            self.connected = False

    async def send_frame(self, data: bytes, destination: str = "RFMP"):
        """
        Send an RFMP frame via Direwolf.

        Args:
            data: RFMP frame data to send
            destination: Destination address (default "RFMP" for broadcast)
        """
        if self.config.offline_mode:
            logger.debug("Offline mode - frame not sent")
            return

        if not self.connected or not self.writer:
            logger.warning("Not connected to Direwolf - frame not sent")
            return

        try:
            # Create AX.25 UI frame
            source = f"{self.config.callsign}"
            if self.config.ssid > 0:
                source += f"-{self.config.ssid}"

            ax25_frame = AX25Frame.create_ui_frame(
                source=source,
                destination=destination,
                info=data
            )

            # Encode to AX.25
            ax25_data = ax25_frame.encode()

            # Encode to KISS
            kiss_data = self.kiss_protocol.encode_data(ax25_data)

            # Send to Direwolf
            self.writer.write(kiss_data)
            await self.writer.drain()

            logger.debug(f"Sent frame: {len(data)} bytes")

        except Exception as e:
            logger.error(f"Error sending frame: {e}")
            self.connected = False

    async def send_raw_kiss(self, data: bytes):
        """
        Send raw KISS data to Direwolf.

        Args:
            data: Raw KISS frame data
        """
        if not self.connected or not self.writer:
            return

        try:
            self.writer.write(data)
            await self.writer.drain()
        except Exception as e:
            logger.error(f"Error sending raw KISS: {e}")
            self.connected = False

    def is_connected(self) -> bool:
        """Check if connected to Direwolf."""
        return self.connected

    async def wait_connected(self, timeout: Optional[float] = None):
        """
        Wait for connection to be established.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            TimeoutError: If timeout expires
        """
        start_time = asyncio.get_event_loop().time()

        while not self.connected:
            if timeout:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError("Timeout waiting for Direwolf connection")

            await asyncio.sleep(0.1)