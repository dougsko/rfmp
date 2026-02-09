"""Data models for RFMP storage."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class MessageRecord:
    """Database record for a message."""
    id: str
    from_node: str
    timestamp: str
    channel: str
    priority: int
    reply_to: Optional[str]
    body: str
    received_at: datetime
    transmitted_at: Optional[datetime] = None
    rebroadcast_count: int = 0
    raw_frame: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'MessageRecord':
        """Create from database row dictionary."""
        return cls(
            id=data['id'],
            from_node=data['from_node'],
            timestamp=data['timestamp'],
            channel=data['channel'],
            priority=data['priority'],
            reply_to=data.get('reply_to'),
            body=data['body'],
            received_at=datetime.fromtimestamp(data['received_at']),
            transmitted_at=datetime.fromtimestamp(data['transmitted_at']) if data.get('transmitted_at') else None,
            rebroadcast_count=data.get('rebroadcast_count', 0),
            raw_frame=data.get('raw_frame')
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            'id': self.id,
            'from_node': self.from_node,
            'timestamp': self.timestamp,
            'channel': self.channel,
            'priority': self.priority,
            'reply_to': self.reply_to,
            'body': self.body,
            'received_at': int(self.received_at.timestamp()),
            'transmitted_at': int(self.transmitted_at.timestamp()) if self.transmitted_at else None,
            'rebroadcast_count': self.rebroadcast_count,
            'raw_frame': self.raw_frame
        }


@dataclass
class FragmentRecord:
    """Database record for a message fragment."""
    message_id: str
    idx: int
    total: int
    data: bytes
    received_at: datetime

    @classmethod
    def from_dict(cls, data: dict) -> 'FragmentRecord':
        """Create from database row dictionary."""
        return cls(
            message_id=data['message_id'],
            idx=data['idx'],
            total=data['total'],
            data=data['data'],
            received_at=datetime.fromtimestamp(data['received_at'])
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            'message_id': self.message_id,
            'idx': self.idx,
            'total': self.total,
            'data': self.data,
            'received_at': int(self.received_at.timestamp())
        }


@dataclass
class NodeRecord:
    """Database record for a seen node."""
    callsign: str
    first_seen: datetime
    last_seen: datetime
    last_sync: Optional[datetime]
    message_count: int
    sync_count: int
    req_count: int
    metadata: Optional[dict] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'NodeRecord':
        """Create from database row dictionary."""
        import json
        return cls(
            callsign=data['callsign'],
            first_seen=datetime.fromtimestamp(data['first_seen']),
            last_seen=datetime.fromtimestamp(data['last_seen']),
            last_sync=datetime.fromtimestamp(data['last_sync']) if data.get('last_sync') else None,
            message_count=data.get('message_count', 0),
            sync_count=data.get('sync_count', 0),
            req_count=data.get('req_count', 0),
            metadata=json.loads(data['metadata']) if data.get('metadata') else None
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        import json
        return {
            'callsign': self.callsign,
            'first_seen': int(self.first_seen.timestamp()),
            'last_seen': int(self.last_seen.timestamp()),
            'last_sync': int(self.last_sync.timestamp()) if self.last_sync else None,
            'message_count': self.message_count,
            'sync_count': self.sync_count,
            'req_count': self.req_count,
            'metadata': json.dumps(self.metadata) if self.metadata else None
        }


@dataclass
class ChannelStats:
    """Statistics for a channel."""
    name: str
    first_message: datetime
    last_message: datetime
    message_count: int
    unique_nodes: int
    metadata: Optional[dict] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'ChannelStats':
        """Create from database row dictionary."""
        import json
        return cls(
            name=data['name'],
            first_message=datetime.fromtimestamp(data['first_message']),
            last_message=datetime.fromtimestamp(data['last_message']),
            message_count=data.get('message_count', 0),
            unique_nodes=data.get('unique_nodes', 0),
            metadata=json.loads(data['metadata']) if data.get('metadata') else None
        )


@dataclass
class RequestTracker:
    """Tracks REQ attempts for rate limiting."""
    message_id: str
    first_request: datetime
    last_request: datetime
    retry_count: int
    backoff_seconds: int
    success: bool

    @classmethod
    def from_dict(cls, data: dict) -> 'RequestTracker':
        """Create from database row dictionary."""
        return cls(
            message_id=data['message_id'],
            first_request=datetime.fromtimestamp(data['first_request']),
            last_request=datetime.fromtimestamp(data['last_request']),
            retry_count=data['retry_count'],
            backoff_seconds=data['backoff_seconds'],
            success=bool(data['success'])
        )

    def can_retry(self) -> bool:
        """Check if we can retry this request."""
        if self.success:
            return False
        if self.retry_count >= 4:  # Max retries
            return False

        # Check backoff period
        next_allowed = self.last_request.timestamp() + self.backoff_seconds
        return datetime.utcnow().timestamp() >= next_allowed


@dataclass
class BloomFilterWindow:
    """Rotating Bloom filter window."""
    window_index: int
    start_time: datetime
    end_time: datetime
    bloom_data: bytes
    message_count: int

    @classmethod
    def from_dict(cls, data: dict) -> 'BloomFilterWindow':
        """Create from database row dictionary."""
        return cls(
            window_index=data['window_index'],
            start_time=datetime.fromtimestamp(data['start_time']),
            end_time=datetime.fromtimestamp(data['end_time']),
            bloom_data=data['bloom_data'],
            message_count=data['message_count']
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            'window_index': self.window_index,
            'start_time': int(self.start_time.timestamp()),
            'end_time': int(self.end_time.timestamp()),
            'bloom_data': self.bloom_data,
            'message_count': self.message_count
        }

    def is_active(self) -> bool:
        """Check if this window is currently active."""
        now = datetime.utcnow()
        return self.start_time <= now < self.end_time