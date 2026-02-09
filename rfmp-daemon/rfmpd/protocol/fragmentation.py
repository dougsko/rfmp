"""Message fragmentation and reassembly."""

import math
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from .frames import MSG, FRAG
from .parser import FrameParser


@dataclass
class FragmentCollector:
    """Collects and reassembles message fragments."""
    message_id: str
    total_fragments: int
    fragments: Dict[int, bytes]
    first_seen: datetime
    timeout: timedelta = timedelta(minutes=5)

    def add_fragment(self, fragment: FRAG) -> bool:
        """
        Add a fragment to the collector.

        Args:
            fragment: Fragment to add

        Returns:
            True if fragment was new, False if duplicate
        """
        if fragment.message_id != self.message_id:
            raise ValueError(f"Fragment {fragment.message_id} doesn't match collector {self.message_id}")

        if fragment.idx in self.fragments:
            return False  # Duplicate

        self.fragments[fragment.idx] = fragment.data
        return True

    def is_complete(self) -> bool:
        """Check if all fragments have been received."""
        return len(self.fragments) == self.total_fragments

    def is_expired(self) -> bool:
        """Check if collector has timed out."""
        return datetime.utcnow() - self.first_seen > self.timeout

    def get_missing_indexes(self) -> List[int]:
        """Get list of missing fragment indexes."""
        return [i for i in range(self.total_fragments) if i not in self.fragments]

    def reassemble(self) -> Optional[bytes]:
        """
        Reassemble complete message from fragments.

        Returns:
            Reassembled message bytes or None if incomplete
        """
        if not self.is_complete():
            return None

        # Sort fragments by index and concatenate
        parts = []
        for i in range(self.total_fragments):
            parts.append(self.fragments[i])

        return b''.join(parts)


class Fragmenter:
    """Handles message fragmentation and reassembly."""

    def __init__(self, fragment_threshold: int = 200):
        """
        Initialize fragmenter.

        Args:
            fragment_threshold: Maximum size before fragmentation
        """
        self.fragment_threshold = fragment_threshold
        self.collectors: Dict[str, FragmentCollector] = {}

    def fragment_message(self, msg: MSG) -> List[FRAG]:
        """
        Fragment a message if needed.

        Args:
            msg: Message to fragment

        Returns:
            List of fragments (empty if no fragmentation needed)
        """
        # Encode the message
        encoded = FrameParser.encode(msg)

        # Check if fragmentation is needed
        if len(encoded) <= self.fragment_threshold:
            return []  # No fragmentation needed

        # Calculate fragment size (leave room for FRAG overhead)
        # FRAG overhead is approximately 50 bytes for headers
        fragment_size = self.fragment_threshold - 50

        # Split into fragments
        fragments = []
        total_fragments = math.ceil(len(encoded) / fragment_size)

        for i in range(total_fragments):
            start = i * fragment_size
            end = min(start + fragment_size, len(encoded))
            data = encoded[start:end]

            fragment = FRAG(
                message_id=msg.id,
                idx=i,
                total=total_fragments,
                data=data
            )
            fragments.append(fragment)

        return fragments

    def add_fragment(self, fragment: FRAG) -> Tuple[bool, Optional[MSG]]:
        """
        Add a fragment and attempt reassembly.

        Args:
            fragment: Fragment to add

        Returns:
            Tuple of (is_new, reassembled_message)
            - is_new: True if fragment was new, False if duplicate
            - reassembled_message: Complete message if all fragments received
        """
        # Get or create collector
        if fragment.message_id not in self.collectors:
            self.collectors[fragment.message_id] = FragmentCollector(
                message_id=fragment.message_id,
                total_fragments=fragment.total,
                fragments={},
                first_seen=datetime.utcnow()
            )

        collector = self.collectors[fragment.message_id]

        # Add fragment
        is_new = collector.add_fragment(fragment)

        # Check if complete
        if collector.is_complete():
            # Reassemble message
            data = collector.reassemble()
            if data:
                # Parse reassembled message
                frame = FrameParser.decode(data)
                if isinstance(frame, MSG):
                    # Clean up collector
                    del self.collectors[fragment.message_id]
                    return is_new, frame

        return is_new, None

    def get_missing_fragments(self, message_id: str) -> Optional[List[int]]:
        """
        Get missing fragment indexes for a message.

        Args:
            message_id: Message ID to check

        Returns:
            List of missing indexes or None if no collector
        """
        if message_id not in self.collectors:
            return None

        return self.collectors[message_id].get_missing_indexes()

    def cleanup_expired(self) -> List[str]:
        """
        Remove expired fragment collectors.

        Returns:
            List of expired message IDs
        """
        expired = []
        for message_id, collector in list(self.collectors.items()):
            if collector.is_expired():
                expired.append(message_id)
                del self.collectors[message_id]

        return expired