"""Adaptive timing for RFMP transmissions."""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class TimingConfig:
    """Configuration for adaptive timing."""
    base_delay: float = 0.2  # Base delay in seconds
    jitter: float = 0.4  # Random jitter range
    priority_step: float = 0.35  # Delay per priority level
    max_priority: int = 3  # Maximum priority value


class AdaptiveTiming:
    """
    Implements adaptive timing for collision reduction.

    Calculates transmission delays based on priority and random jitter
    to reduce the likelihood of packet collisions on shared RF medium.
    """

    def __init__(self, config: Optional[TimingConfig] = None):
        """
        Initialize adaptive timing.

        Args:
            config: Timing configuration (uses defaults if None)
        """
        self.config = config or TimingConfig()

    def calculate_delay(self, priority: int = 1) -> float:
        """
        Calculate transmission delay for a given priority.

        Formula: delay = base + random(0, jitter) + (MAX_PRIO - prio) * PRIO_STEP

        Args:
            priority: Message priority (0=highest, 3=lowest)

        Returns:
            Delay in seconds before transmission
        """
        # Validate priority
        if not 0 <= priority <= self.config.max_priority:
            raise ValueError(f"Priority must be 0-{self.config.max_priority}")

        # Calculate components
        base = self.config.base_delay
        jitter = random.uniform(0, self.config.jitter)
        priority_delay = (self.config.max_priority - priority) * self.config.priority_step

        # Total delay
        delay = base + jitter + priority_delay

        return delay

    def calculate_sync_delay(self) -> float:
        """
        Calculate delay for SYNC frame transmission.

        SYNC frames use medium priority with extra jitter.

        Returns:
            Delay in seconds
        """
        # SYNC frames use priority 2 (medium-low)
        base_delay = self.calculate_delay(priority=2)

        # Add extra jitter for SYNC to spread them out
        extra_jitter = random.uniform(0, 2.0)

        return base_delay + extra_jitter

    def calculate_req_delay(self, retry_count: int = 0) -> float:
        """
        Calculate delay for REQ frame transmission.

        REQ frames use low priority with exponential backoff.

        Args:
            retry_count: Number of previous attempts

        Returns:
            Delay in seconds
        """
        # REQ frames use priority 3 (lowest)
        base_delay = self.calculate_delay(priority=3)

        # Add exponential backoff based on retry count
        backoff = min(60, (2 ** retry_count) * 1.0)

        return base_delay + backoff

    def calculate_fragment_delay(self, fragment_index: int, total_fragments: int) -> float:
        """
        Calculate delay for fragment transmission.

        Fragments are sent with small inter-fragment delays.

        Args:
            fragment_index: Index of this fragment
            total_fragments: Total number of fragments

        Returns:
            Delay in seconds
        """
        if fragment_index == 0:
            # First fragment uses normal priority-based delay
            return self.calculate_delay(priority=1)
        else:
            # Subsequent fragments use small fixed delay
            # This keeps fragments together while avoiding collisions
            return 0.05 + random.uniform(0, 0.05)

    def calculate_rebroadcast_delay(self, priority: int = 1) -> float:
        """
        Calculate delay for rebroadcasting received messages.

        Rebroadcasts use longer delays to let original transmission complete.

        Args:
            priority: Message priority

        Returns:
            Delay in seconds
        """
        # Base delay for rebroadcast
        base_delay = self.calculate_delay(priority)

        # Add extra delay for rebroadcasts
        rebroadcast_delay = random.uniform(1.0, 3.0)

        return base_delay + rebroadcast_delay

    def update_config(self, config: TimingConfig):
        """
        Update timing configuration.

        Args:
            config: New timing configuration
        """
        self.config = config

    def get_stats(self) -> dict:
        """
        Get timing statistics.

        Returns:
            Dictionary with timing stats
        """
        return {
            'base_delay': self.config.base_delay,
            'jitter': self.config.jitter,
            'priority_step': self.config.priority_step,
            'max_priority': self.config.max_priority,
            'priority_delays': {
                f'priority_{p}': {
                    'min': self.config.base_delay + (self.config.max_priority - p) * self.config.priority_step,
                    'max': self.config.base_delay + self.config.jitter + (self.config.max_priority - p) * self.config.priority_step
                }
                for p in range(self.config.max_priority + 1)
            }
        }