"""Bloom filter implementation for RFMP synchronization."""

import mmh3
from typing import List, Tuple
from datetime import datetime, timedelta
import struct


class BloomFilter:
    """Simple Bloom filter implementation."""

    def __init__(self, num_bits: int = 256, num_hashes: int = 3):
        """
        Initialize Bloom filter.

        Args:
            num_bits: Size of the bit array (must be multiple of 8)
            num_hashes: Number of hash functions to use
        """
        if num_bits % 8 != 0:
            raise ValueError("num_bits must be a multiple of 8")

        self.num_bits = num_bits
        self.num_hashes = num_hashes
        self.num_bytes = num_bits // 8

        # Initialize bit array as bytes
        self.bits = bytearray(self.num_bytes)

    def add(self, item: str):
        """
        Add an item to the Bloom filter.

        Args:
            item: Item to add (typically a message ID)
        """
        for seed in range(self.num_hashes):
            # Get hash value
            hash_val = mmh3.hash(item, seed, signed=False)

            # Map to bit position
            bit_pos = hash_val % self.num_bits

            # Set the bit
            byte_idx = bit_pos // 8
            bit_idx = bit_pos % 8
            self.bits[byte_idx] |= (1 << bit_idx)

    def contains(self, item: str) -> bool:
        """
        Check if an item might be in the filter.

        Args:
            item: Item to check

        Returns:
            True if item might be present, False if definitely not
        """
        for seed in range(self.num_hashes):
            # Get hash value
            hash_val = mmh3.hash(item, seed, signed=False)

            # Map to bit position
            bit_pos = hash_val % self.num_bits

            # Check the bit
            byte_idx = bit_pos // 8
            bit_idx = bit_pos % 8

            if not (self.bits[byte_idx] & (1 << bit_idx)):
                return False  # Definitely not in the filter

        return True  # Might be in the filter

    def to_bytes(self) -> bytes:
        """
        Serialize Bloom filter to bytes.

        Returns:
            Serialized filter as bytes
        """
        return bytes(self.bits)

    @classmethod
    def from_bytes(cls, data: bytes, num_hashes: int = 3) -> 'BloomFilter':
        """
        Deserialize Bloom filter from bytes.

        Args:
            data: Serialized filter data
            num_hashes: Number of hash functions

        Returns:
            Deserialized Bloom filter
        """
        num_bits = len(data) * 8
        bf = cls(num_bits=num_bits, num_hashes=num_hashes)
        bf.bits = bytearray(data)
        return bf

    def clear(self):
        """Clear all bits in the filter."""
        self.bits = bytearray(self.num_bytes)

    def count_set_bits(self) -> int:
        """Count the number of set bits (for statistics)."""
        count = 0
        for byte in self.bits:
            count += bin(byte).count('1')
        return count

    def fill_rate(self) -> float:
        """Calculate the fill rate of the filter."""
        return self.count_set_bits() / self.num_bits


class RotatingBloomFilter:
    """
    Rotating Bloom filter with time-based windows.

    Maintains multiple Bloom filters for different time windows,
    rotating them as time progresses.
    """

    def __init__(self,
                 window_duration: int = 600,
                 window_count: int = 3,
                 bloom_bits: int = 256,
                 bloom_hashes: int = 3):
        """
        Initialize rotating Bloom filter.

        Args:
            window_duration: Duration of each window in seconds
            window_count: Number of windows to maintain
            bloom_bits: Size of each Bloom filter in bits
            bloom_hashes: Number of hash functions
        """
        self.window_duration = window_duration
        self.window_count = window_count
        self.bloom_bits = bloom_bits
        self.bloom_hashes = bloom_hashes

        # Initialize windows
        self.windows: List[Tuple[datetime, BloomFilter]] = []
        self._initialize_windows()

        # Track current window index
        self.current_window_index = 0

    def _initialize_windows(self):
        """Initialize time windows with empty Bloom filters."""
        now = datetime.utcnow()

        for i in range(self.window_count):
            # Calculate window start time
            window_start = now - timedelta(seconds=i * self.window_duration)

            # Create empty Bloom filter
            bloom = BloomFilter(
                num_bits=self.bloom_bits,
                num_hashes=self.bloom_hashes
            )

            self.windows.append((window_start, bloom))

    def _rotate_if_needed(self):
        """Rotate windows if the oldest has expired."""
        now = datetime.utcnow()

        # Check if oldest window has expired
        oldest_start, _ = self.windows[-1]
        age = now - oldest_start

        if age > timedelta(seconds=self.window_duration * self.window_count):
            # Rotate: remove oldest, add new
            self.windows.pop()

            # Create new window
            new_bloom = BloomFilter(
                num_bits=self.bloom_bits,
                num_hashes=self.bloom_hashes
            )
            self.windows.insert(0, (now, new_bloom))

            # Update current window index
            self.current_window_index = (self.current_window_index + 1) % self.window_count

    def add(self, item: str):
        """
        Add an item to the current window.

        Args:
            item: Item to add (typically a message ID)
        """
        self._rotate_if_needed()

        # Add to current (most recent) window
        _, bloom = self.windows[0]
        bloom.add(item)

    def contains(self, item: str) -> bool:
        """
        Check if an item is in any window.

        Args:
            item: Item to check

        Returns:
            True if item might be present in any window
        """
        self._rotate_if_needed()

        # Check all windows
        for _, bloom in self.windows:
            if bloom.contains(item):
                return True

        return False

    def get_filters(self) -> List[bytes]:
        """
        Get serialized Bloom filters for SYNC frame.

        Returns:
            List of serialized Bloom filters (oldest to newest)
        """
        self._rotate_if_needed()

        # Return filters in reverse order (oldest first)
        filters = []
        for _, bloom in reversed(self.windows):
            filters.append(bloom.to_bytes())

        return filters

    def get_current_window_index(self) -> int:
        """
        Get the current window index for SYNC frame.

        Returns:
            Current window index (0-2)
        """
        return self.current_window_index

    def compare_filters(self, remote_filters: List[bytes]) -> List[str]:
        """
        Compare with remote Bloom filters to find potential missing messages.

        Args:
            remote_filters: List of serialized Bloom filters from remote node

        Returns:
            List of potentially missing message IDs
        """
        # This would need access to the message database
        # to check which messages we have that aren't in remote filters
        # For now, return empty list - this will be implemented
        # when integrating with the database
        return []

    def get_stats(self) -> dict:
        """
        Get statistics about the rotating filter.

        Returns:
            Dictionary with statistics
        """
        stats = {
            'window_count': self.window_count,
            'window_duration': self.window_duration,
            'current_index': self.current_window_index,
            'windows': []
        }

        for start_time, bloom in self.windows:
            window_stats = {
                'start_time': start_time.isoformat(),
                'fill_rate': bloom.fill_rate(),
                'set_bits': bloom.count_set_bits()
            }
            stats['windows'].append(window_stats)

        return stats