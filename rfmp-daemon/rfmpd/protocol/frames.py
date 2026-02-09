"""RFMP frame type definitions."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
import base64


class FrameType(Enum):
    """RFMP frame types."""
    MSG = "MSG"
    FRAG = "FRAG"
    SYNC = "SYNC"
    REQ = "REQ"


class Frame:
    """Base class for RFMP frames."""
    frame_type: FrameType = None

    def to_dict(self) -> dict:
        """Convert frame to dictionary for encoding."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict):
        """Create frame from dictionary."""
        raise NotImplementedError


@dataclass
class MSG(Frame):
    """Message frame."""
    id: str  # 8-12 char hex message ID
    from_node: str  # Callsign with optional SSID
    timestamp: str  # YYYYMMDDTHHMMSSZ format
    channel: str  # ASCII lowercase channel name
    priority: int  # 0-3 priority level
    reply_to: Optional[str]  # Message ID or None
    body: str  # UTF-8 message text

    def __post_init__(self):
        self.frame_type = FrameType.MSG
        # Validate fields
        if not 8 <= len(self.id) <= 12:
            raise ValueError(f"Message ID must be 8-12 characters, got {len(self.id)}")
        if not 0 <= self.priority <= 3:
            raise ValueError(f"Priority must be 0-3, got {self.priority}")
        if not self.channel.islower() or not self.channel.isascii():
            raise ValueError(f"Channel must be ASCII lowercase, got {self.channel}")

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'from': self.from_node,
            'time': self.timestamp,
            'chan': self.channel,
            'prio': str(self.priority),
            'reply': self.reply_to or '-',
            'body': self.body
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data['id'],
            from_node=data['from'],
            timestamp=data['time'],
            channel=data['chan'],
            priority=int(data['prio']),
            reply_to=data['reply'] if data['reply'] != '-' else None,
            body=data['body']
        )


@dataclass
class FRAG(Frame):
    """Fragment frame."""
    message_id: str  # Message ID this fragment belongs to
    idx: int  # 0-based fragment index
    total: int  # Total number of fragments
    data: bytes  # Fragment payload (base64 encoded in wire format)

    def __post_init__(self):
        self.frame_type = FrameType.FRAG
        if self.idx < 0 or self.idx >= self.total:
            raise ValueError(f"Invalid fragment index {self.idx}/{self.total}")

    def to_dict(self) -> dict:
        return {
            'msgid': self.message_id,
            'idx': str(self.idx),
            'total': str(self.total),
            'data': base64.b64encode(self.data).decode('ascii')
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            message_id=data['msgid'],
            idx=int(data['idx']),
            total=int(data['total']),
            data=base64.b64decode(data['data'])
        )


@dataclass
class SYNC(Frame):
    """Synchronization frame with rotating Bloom filters."""
    from_node: str  # Node ID sending the sync
    bloom_filters: List[bytes]  # 3 Bloom filters (base64 encoded in wire format)
    window_index: int  # Current window index (0-2)

    def __post_init__(self):
        self.frame_type = FrameType.SYNC
        if len(self.bloom_filters) != 3:
            raise ValueError("SYNC frame must have exactly 3 Bloom filters")
        if not 0 <= self.window_index <= 2:
            raise ValueError(f"Window index must be 0-2, got {self.window_index}")

    def to_dict(self) -> dict:
        return {
            'from': self.from_node,
            'bf0': base64.b64encode(self.bloom_filters[0]).decode('ascii'),
            'bf1': base64.b64encode(self.bloom_filters[1]).decode('ascii'),
            'bf2': base64.b64encode(self.bloom_filters[2]).decode('ascii'),
            'win': str(self.window_index)
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            from_node=data['from'],
            bloom_filters=[
                base64.b64decode(data['bf0']),
                base64.b64decode(data['bf1']),
                base64.b64decode(data['bf2'])
            ],
            window_index=int(data['win'])
        )


@dataclass
class REQ(Frame):
    """Request frame for missing messages."""
    from_node: str  # Node requesting the message
    message_id: str  # Message ID being requested
    missing_fragments: Optional[List[int]]  # Specific fragment indexes if partial

    def __post_init__(self):
        self.frame_type = FrameType.REQ

    def to_dict(self) -> dict:
        result = {
            'from': self.from_node,
            'msgid': self.message_id
        }
        if self.missing_fragments:
            result['missing'] = ','.join(str(i) for i in self.missing_fragments)
        return result

    @classmethod
    def from_dict(cls, data: dict):
        missing = None
        if 'missing' in data:
            missing = [int(i) for i in data['missing'].split(',')]
        return cls(
            from_node=data['from'],
            message_id=data['msgid'],
            missing_fragments=missing
        )