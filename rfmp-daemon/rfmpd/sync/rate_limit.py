"""Rate limiting for REQ frames."""

from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, field


@dataclass
class RequestRecord:
    """Record of a REQ attempt."""
    message_id: str
    first_attempt: datetime
    last_attempt: datetime
    attempt_count: int
    backoff_seconds: int


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_req_per_min: int = 6  # Global rate limit
    initial_backoff: int = 30  # Initial backoff in seconds
    max_backoff: int = 600  # Maximum backoff in seconds
    max_retries: int = 4  # Maximum retries per message


class RateLimiter:
    """
    Rate limiter for REQ frame transmission.

    Implements both global rate limiting and per-message backoff.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration (uses defaults if None)
        """
        self.config = config or RateLimitConfig()

        # Track request history
        self.request_history: List[datetime] = []

        # Track per-message requests
        self.message_requests: Dict[str, RequestRecord] = {}

    def can_send_req(self, message_id: Optional[str] = None) -> bool:
        """
        Check if a REQ can be sent.

        Args:
            message_id: Optional message ID for per-message checking

        Returns:
            True if REQ can be sent, False otherwise
        """
        # Check global rate limit
        if not self._check_global_limit():
            return False

        # Check per-message limit if ID provided
        if message_id and not self._check_message_limit(message_id):
            return False

        return True

    def _check_global_limit(self) -> bool:
        """Check global REQ rate limit."""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)

        # Remove old entries
        self.request_history = [
            ts for ts in self.request_history
            if ts > cutoff
        ]

        # Check count
        return len(self.request_history) < self.config.max_req_per_min

    def _check_message_limit(self, message_id: str) -> bool:
        """Check per-message rate limit and backoff."""
        if message_id not in self.message_requests:
            return True  # First request for this message

        record = self.message_requests[message_id]

        # Check max retries
        if record.attempt_count >= self.config.max_retries:
            return False

        # Check backoff period
        now = datetime.utcnow()
        next_allowed = record.last_attempt + timedelta(seconds=record.backoff_seconds)

        return now >= next_allowed

    def record_req(self, message_id: str):
        """
        Record that a REQ was sent.

        Args:
            message_id: Message ID being requested
        """
        now = datetime.utcnow()

        # Add to global history
        self.request_history.append(now)

        # Update per-message record
        if message_id in self.message_requests:
            record = self.message_requests[message_id]
            record.last_attempt = now
            record.attempt_count += 1

            # Exponential backoff
            record.backoff_seconds = min(
                self.config.max_backoff,
                record.backoff_seconds * 2
            )
        else:
            # First request for this message
            self.message_requests[message_id] = RequestRecord(
                message_id=message_id,
                first_attempt=now,
                last_attempt=now,
                attempt_count=1,
                backoff_seconds=self.config.initial_backoff
            )

    def mark_success(self, message_id: str):
        """
        Mark that a message was successfully received.

        Args:
            message_id: Message ID that was received
        """
        # Remove from tracking
        if message_id in self.message_requests:
            del self.message_requests[message_id]

    def get_backoff(self, message_id: str) -> Optional[int]:
        """
        Get current backoff period for a message.

        Args:
            message_id: Message ID to check

        Returns:
            Backoff period in seconds, or None if no record
        """
        if message_id in self.message_requests:
            return self.message_requests[message_id].backoff_seconds
        return None

    def get_next_req_time(self, message_id: Optional[str] = None) -> Optional[datetime]:
        """
        Get the next time a REQ can be sent.

        Args:
            message_id: Optional message ID for specific checking

        Returns:
            Next allowed time, or None if can send now
        """
        # Check global limit
        if len(self.request_history) >= self.config.max_req_per_min:
            # Find when oldest request expires
            if self.request_history:
                oldest = min(self.request_history)
                return oldest + timedelta(minutes=1)

        # Check message-specific limit
        if message_id and message_id in self.message_requests:
            record = self.message_requests[message_id]

            if record.attempt_count >= self.config.max_retries:
                return None  # Never (max retries reached)

            next_time = record.last_attempt + timedelta(seconds=record.backoff_seconds)
            return next_time

        return None  # Can send now

    def cleanup_old_records(self, max_age_hours: int = 24):
        """
        Remove old request records.

        Args:
            max_age_hours: Maximum age in hours
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        # Remove old message requests
        self.message_requests = {
            msg_id: record
            for msg_id, record in self.message_requests.items()
            if record.last_attempt > cutoff
        }

    def get_stats(self) -> dict:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with statistics
        """
        now = datetime.utcnow()
        recent_cutoff = now - timedelta(minutes=1)

        recent_count = sum(
            1 for ts in self.request_history
            if ts > recent_cutoff
        )

        return {
            'config': {
                'max_req_per_min': self.config.max_req_per_min,
                'initial_backoff': self.config.initial_backoff,
                'max_backoff': self.config.max_backoff,
                'max_retries': self.config.max_retries
            },
            'current': {
                'recent_requests': recent_count,
                'tracked_messages': len(self.message_requests),
                'can_send_global': recent_count < self.config.max_req_per_min
            }
        }