"""RFMP message model and ID generation."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


def generate_message_id(sender: str, timestamp: str, body: str) -> str:
    """
    Generate a message ID from content.

    Args:
        sender: The display sender (author/nickname) or node callsign used
            when creating the message. This allows IDs to incorporate
            the application-level `author` when provided.
        timestamp: Message timestamp in YYYYMMDDTHHMMSSZ format
        body: Message body text

    Returns:
        8-12 character hex string ID
    """

    # Concatenate the fields for hashing
    content = f"{sender}{timestamp}{body}"

    # Generate SHA256 hash
    hash_obj = hashlib.sha256(content.encode('utf-8'))

    # Take first 12 hex characters (48 bits)
    # This gives us reasonable uniqueness while keeping IDs short
    message_id = hash_obj.hexdigest()[:12]

    return message_id


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """
    Format a datetime as RFMP timestamp.

    Args:
        dt: Datetime to format (uses current UTC if None)

    Returns:
        Timestamp in YYYYMMDDTHHMMSSZ format
    """
    if dt is None:
        dt = datetime.utcnow()

    return dt.strftime("%Y%m%dT%H%M%SZ")


def parse_timestamp(timestamp: str) -> datetime:
    """
    Parse RFMP timestamp to datetime.

    Args:
        timestamp: Timestamp in YYYYMMDDTHHMMSSZ format

    Returns:
        Parsed datetime object
    """
    return datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ")


@dataclass
class Message:
    """
    High-level message representation.

    This class represents a complete message with all metadata,
    as opposed to the MSG frame which is the wire format.
    """
    id: str
    from_node: str
    timestamp: str
    channel: str
    priority: int
    reply_to: Optional[str]
    body: str
    received_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate message fields."""
        if not 8 <= len(self.id) <= 12:
            raise ValueError(f"Message ID must be 8-12 characters")

        if not 0 <= self.priority <= 3:
            raise ValueError(f"Priority must be 0-3")

        if not self.channel.islower() or not self.channel.isascii():
            raise ValueError(f"Channel must be ASCII lowercase")

        # Validate timestamp format
        try:
            parse_timestamp(self.timestamp)
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {self.timestamp}")

    @classmethod
    def create(cls,
               from_node: str,
               channel: str,
               body: str,
               priority: int = 1,
               reply_to: Optional[str] = None,
               timestamp: Optional[str] = None,
               author: Optional[str] = None) -> 'Message':
        """
        Create a new message with auto-generated ID.

        Args:
            from_node: Sender's callsign
            channel: Channel name
            body: Message text
            priority: Priority level (0-3)
            reply_to: Optional message ID being replied to
            timestamp: Optional timestamp (auto-generated if None)

        Returns:
            New Message instance
        """
        if timestamp is None:
            timestamp = format_timestamp()

        # Use author (application-level display name) for ID generation if
        # provided; otherwise fall back to the node callsign
        sender_for_id = author or from_node
        message_id = generate_message_id(sender_for_id, timestamp, body)

        return cls(
            id=message_id,
            from_node=from_node,
            timestamp=timestamp,
            channel=channel,
            priority=priority,
            reply_to=reply_to,
            body=body,
            received_at=datetime.utcnow()
        )

    def to_frame(self):
        """Convert to MSG frame for transmission."""
        from .frames import MSG
        return MSG(
            id=self.id,
            from_node=self.from_node,
            timestamp=self.timestamp,
            channel=self.channel,
            priority=self.priority,
            reply_to=self.reply_to,
            body=self.body
        )

    def needs_fragmentation(self, threshold: int = 200) -> bool:
        """Check if message needs fragmentation."""
        # Estimate encoded size
        frame = self.to_frame()
        encoded = str(frame.to_dict())
        return len(encoded.encode('utf-8')) > threshold