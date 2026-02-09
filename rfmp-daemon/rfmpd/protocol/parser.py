"""RFMP frame parser for encoding and decoding wire format."""

from typing import Dict, Optional, Union
from .frames import Frame, FrameType, MSG, FRAG, SYNC, REQ


class FrameParser:
    """Parser for RFMP wire format."""

    @staticmethod
    def encode(frame: Frame) -> bytes:
        """
        Encode a frame to RFMP wire format.

        Format: TYPE|key=value|key=value|...

        Args:
            frame: Frame to encode

        Returns:
            Encoded frame as bytes
        """
        # Get frame type
        frame_type = frame.frame_type.value

        # Get frame fields as dictionary
        fields = frame.to_dict()

        # Build the encoded string
        parts = [frame_type]
        for key, value in fields.items():
            parts.append(f"{key}={value}")

        # Join with pipe delimiter
        encoded = '|'.join(parts)

        return encoded.encode('utf-8')

    @staticmethod
    def decode(data: bytes) -> Optional[Frame]:
        """
        Decode RFMP wire format to a frame.

        Args:
            data: Raw frame bytes

        Returns:
            Decoded frame or None if invalid
        """
        try:
            # Decode bytes to string
            text = data.decode('utf-8')

            # Split by pipe delimiter
            parts = text.split('|')

            if len(parts) < 2:
                return None

            # First part is frame type
            frame_type_str = parts[0]

            # Parse frame type
            try:
                frame_type = FrameType(frame_type_str)
            except ValueError:
                return None

            # Parse key=value pairs
            fields: Dict[str, str] = {}
            for part in parts[1:]:
                if '=' not in part:
                    continue
                key, value = part.split('=', 1)
                fields[key] = value

            # Create appropriate frame based on type
            if frame_type == FrameType.MSG:
                return MSG.from_dict(fields)
            elif frame_type == FrameType.FRAG:
                return FRAG.from_dict(fields)
            elif frame_type == FrameType.SYNC:
                return SYNC.from_dict(fields)
            elif frame_type == FrameType.REQ:
                return REQ.from_dict(fields)
            else:
                return None

        except Exception:
            # Return None for any parsing errors
            return None

    @staticmethod
    def validate_frame(frame: Frame) -> bool:
        """
        Validate that a frame meets protocol requirements.

        Args:
            frame: Frame to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            if isinstance(frame, MSG):
                # Validate MSG frame
                if not 8 <= len(frame.id) <= 12:
                    return False
                if not 0 <= frame.priority <= 3:
                    return False
                if not frame.channel.islower() or not frame.channel.isascii():
                    return False
                # Validate timestamp format
                if len(frame.timestamp) != 16 or frame.timestamp[8] != 'T' or frame.timestamp[-1] != 'Z':
                    return False

            elif isinstance(frame, FRAG):
                # Validate FRAG frame
                if frame.idx < 0 or frame.idx >= frame.total:
                    return False
                if frame.total <= 0:
                    return False

            elif isinstance(frame, SYNC):
                # Validate SYNC frame
                if len(frame.bloom_filters) != 3:
                    return False
                if not 0 <= frame.window_index <= 2:
                    return False
                # Check Bloom filter sizes (256 bits = 32 bytes)
                for bf in frame.bloom_filters:
                    if len(bf) != 32:
                        return False

            elif isinstance(frame, REQ):
                # Validate REQ frame
                if not frame.message_id:
                    return False

            return True

        except Exception:
            return False