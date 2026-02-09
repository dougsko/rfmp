"""KISS protocol implementation for TNC communication."""

from typing import List, Optional
from dataclasses import dataclass
from enum import IntEnum


class KISSCommand(IntEnum):
    """KISS command types."""
    DATA_FRAME = 0x00
    TX_DELAY = 0x01
    PERSISTENCE = 0x02
    SLOT_TIME = 0x03
    TX_TAIL = 0x04
    FULL_DUPLEX = 0x05
    SET_HARDWARE = 0x06
    RETURN = 0x0F


# KISS special bytes
FEND = 0xC0  # Frame end
FESC = 0xDB  # Frame escape
TFEND = 0xDC  # Transposed frame end
TFESC = 0xDD  # Transposed frame escape


@dataclass
class KISSFrame:
    """Represents a KISS frame."""
    port: int
    command: KISSCommand
    data: bytes

    def encode(self) -> bytes:
        """Encode frame to KISS protocol bytes."""
        # Combine port and command into command byte
        cmd_byte = (self.port << 4) | self.command

        # Build frame content
        content = bytes([cmd_byte]) + self.data

        # Escape special bytes
        escaped = bytearray()
        for byte in content:
            if byte == FEND:
                escaped.extend([FESC, TFEND])
            elif byte == FESC:
                escaped.extend([FESC, TFESC])
            else:
                escaped.append(byte)

        # Add frame delimiters
        return bytes([FEND]) + bytes(escaped) + bytes([FEND])

    @classmethod
    def decode(cls, data: bytes) -> Optional['KISSFrame']:
        """Decode KISS protocol bytes to frame."""
        if not data:
            return None

        # Remove FEND delimiters
        if data[0] == FEND:
            data = data[1:]
        if data and data[-1] == FEND:
            data = data[:-1]

        if not data:
            return None

        # Unescape special bytes
        unescaped = bytearray()
        i = 0
        while i < len(data):
            if data[i] == FESC:
                if i + 1 < len(data):
                    if data[i + 1] == TFEND:
                        unescaped.append(FEND)
                        i += 2
                    elif data[i + 1] == TFESC:
                        unescaped.append(FESC)
                        i += 2
                    else:
                        # Invalid escape sequence
                        return None
                else:
                    # Incomplete escape sequence
                    return None
            else:
                unescaped.append(data[i])
                i += 1

        if not unescaped:
            return None

        # Extract command byte
        cmd_byte = unescaped[0]
        port = (cmd_byte >> 4) & 0x0F
        command = KISSCommand(cmd_byte & 0x0F)

        # Extract data
        frame_data = bytes(unescaped[1:])

        return cls(port=port, command=command, data=frame_data)


class KISSProtocol:
    """KISS protocol handler."""

    def __init__(self, port: int = 0):
        """
        Initialize KISS protocol handler.

        Args:
            port: KISS port number (0-15)
        """
        self.port = port
        self.buffer = bytearray()

    def encode_data(self, data: bytes) -> bytes:
        """
        Encode data as KISS data frame.

        Args:
            data: Raw data to encode

        Returns:
            KISS-encoded frame bytes
        """
        frame = KISSFrame(
            port=self.port,
            command=KISSCommand.DATA_FRAME,
            data=data
        )
        return frame.encode()

    def decode_frames(self, data: bytes) -> List[KISSFrame]:
        """
        Decode received bytes into KISS frames.

        Args:
            data: Received bytes

        Returns:
            List of decoded frames
        """
        self.buffer.extend(data)
        frames = []

        # Look for complete frames
        while FEND in self.buffer:
            # Find frame boundaries
            start_idx = self.buffer.find(FEND)

            # Skip to next FEND
            end_idx = self.buffer.find(FEND, start_idx + 1)

            if end_idx == -1:
                # No complete frame yet
                break

            # Extract frame including FENDs
            frame_data = bytes(self.buffer[start_idx:end_idx + 1])

            # Remove from buffer
            self.buffer = self.buffer[end_idx + 1:]

            # Decode frame
            frame = KISSFrame.decode(frame_data)
            if frame and frame.command == KISSCommand.DATA_FRAME:
                frames.append(frame)

        return frames

    def set_tx_delay(self, delay_ms: int) -> bytes:
        """
        Create KISS command to set TX delay.

        Args:
            delay_ms: Delay in milliseconds (0-2550)

        Returns:
            KISS command frame
        """
        # Convert to 10ms units
        delay_units = min(255, delay_ms // 10)

        frame = KISSFrame(
            port=self.port,
            command=KISSCommand.TX_DELAY,
            data=bytes([delay_units])
        )
        return frame.encode()

    def set_persistence(self, p: float) -> bytes:
        """
        Create KISS command to set persistence parameter.

        Args:
            p: Persistence value (0.0-1.0)

        Returns:
            KISS command frame
        """
        # Convert to 0-255 range
        p_value = int(p * 255)

        frame = KISSFrame(
            port=self.port,
            command=KISSCommand.PERSISTENCE,
            data=bytes([p_value])
        )
        return frame.encode()

    def set_slot_time(self, slot_ms: int) -> bytes:
        """
        Create KISS command to set slot time.

        Args:
            slot_ms: Slot time in milliseconds (0-2550)

        Returns:
            KISS command frame
        """
        # Convert to 10ms units
        slot_units = min(255, slot_ms // 10)

        frame = KISSFrame(
            port=self.port,
            command=KISSCommand.SLOT_TIME,
            data=bytes([slot_units])
        )
        return frame.encode()