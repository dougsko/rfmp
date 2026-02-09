"""SQLite database interface for RFMP daemon."""

import os
import aiosqlite
from pathlib import Path
from typing import List, Optional, Dict, Any
import json
from datetime import datetime, timedelta


class Database:
    """Async SQLite database handler."""

    def __init__(self, db_path: str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        # Expand user path
        db_path = os.path.expanduser(db_path)

        # Create directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Establish database connection and create tables."""
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

        # Enable foreign keys
        await self.conn.execute("PRAGMA foreign_keys = ON")

        # Create tables
        await self._create_tables()
        await self.conn.commit()

    async def disconnect(self):
        """Close database connection."""
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def _create_tables(self):
        """Create all database tables."""

        # Messages table - stores complete messages
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,                -- 8-12 char hex message ID
                from_node TEXT NOT NULL,            -- Callsign with optional SSID
                author TEXT,                        -- Optional web-session nickname
                timestamp TEXT NOT NULL,            -- YYYYMMDDTHHMMSSZ format
                channel TEXT NOT NULL,              -- Channel name
                priority INTEGER NOT NULL,          -- Priority 0-3
                reply_to TEXT,                      -- Message ID being replied to
                body TEXT NOT NULL,                 -- Message text
                received_at INTEGER NOT NULL,       -- Unix timestamp when received
                transmitted_at INTEGER,             -- Unix timestamp when transmitted
                rebroadcast_count INTEGER DEFAULT 0, -- Number of times rebroadcasted
                raw_frame TEXT,                     -- Original frame data for debugging
                FOREIGN KEY (reply_to) REFERENCES messages(id)
            )
        """)

        # Create indexes for common queries
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp DESC)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_channel
            ON messages(channel)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_from_node
            ON messages(from_node)
        """)

        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_received_at
            ON messages(received_at DESC)
        """)

        # Fragments table - tracks message fragments for reassembly
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fragments (
                message_id TEXT NOT NULL,           -- Message this fragment belongs to
                idx INTEGER NOT NULL,               -- Fragment index (0-based)
                total INTEGER NOT NULL,             -- Total number of fragments
                data BLOB NOT NULL,                 -- Fragment data
                received_at INTEGER NOT NULL,       -- Unix timestamp when received
                PRIMARY KEY (message_id, idx)
            )
        """)

        # Nodes table - tracks seen nodes and their activity
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                callsign TEXT PRIMARY KEY,          -- Node callsign with SSID
                first_seen INTEGER NOT NULL,        -- Unix timestamp of first activity
                last_seen INTEGER NOT NULL,         -- Unix timestamp of last activity
                last_sync INTEGER,                  -- Unix timestamp of last SYNC frame
                message_count INTEGER DEFAULT 0,    -- Total messages from this node
                sync_count INTEGER DEFAULT 0,       -- Total SYNC frames from this node
                req_count INTEGER DEFAULT 0,        -- Total REQ frames from this node
                metadata TEXT                       -- JSON field for additional data
            )
        """)

        # Channels table - tracks channel statistics
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                name TEXT PRIMARY KEY,               -- Channel name
                first_message INTEGER NOT NULL,     -- Unix timestamp of first message
                last_message INTEGER NOT NULL,      -- Unix timestamp of last message
                message_count INTEGER DEFAULT 0,    -- Total messages in channel
                unique_nodes INTEGER DEFAULT 0,     -- Number of unique nodes
                metadata TEXT                       -- JSON field for additional data
            )
        """)

        # Request tracking table - manages REQ rate limiting and backoff
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS request_tracking (
                message_id TEXT PRIMARY KEY,        -- Message ID being requested
                first_request INTEGER NOT NULL,     -- Unix timestamp of first request
                last_request INTEGER NOT NULL,      -- Unix timestamp of last request
                retry_count INTEGER DEFAULT 0,      -- Number of retries
                backoff_seconds INTEGER DEFAULT 30, -- Current backoff period
                success INTEGER DEFAULT 0           -- Whether message was received
            )
        """)

        # Users table - aggregate user statistics by application-level author
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,        -- Application-level nickname
                first_seen INTEGER NOT NULL,      -- Unix timestamp of first activity
                last_seen INTEGER NOT NULL,       -- Unix timestamp of last activity
                message_count INTEGER DEFAULT 0,  -- Messages posted by this user
                last_activity TEXT,               -- JSON metadata or last activity
                metadata TEXT                      -- JSON field for additional data
            )
        """)

        # Bloom filter windows - tracks rotating bloom filter state
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bloom_windows (
                window_index INTEGER PRIMARY KEY,   -- Window index (0-2)
                start_time INTEGER NOT NULL,        -- Window start timestamp
                end_time INTEGER NOT NULL,          -- Window end timestamp
                bloom_data BLOB NOT NULL,           -- Serialized bloom filter
                message_count INTEGER DEFAULT 0     -- Messages in this window
            )
        """)

        # Transmission queue - messages waiting to be transmitted
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS transmission_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_type TEXT NOT NULL,           -- MSG, FRAG, SYNC, REQ
                frame_data TEXT NOT NULL,           -- Serialized frame data
                priority INTEGER DEFAULT 1,         -- Transmission priority
                scheduled_at INTEGER NOT NULL,      -- When to transmit (with timing)
                created_at INTEGER NOT NULL,        -- When queued
                attempts INTEGER DEFAULT 0,         -- Transmission attempts
                status TEXT DEFAULT 'pending'       -- pending, transmitting, sent, failed
            )
        """)

        # Create index for transmission queue
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transmission_queue_scheduled
            ON transmission_queue(scheduled_at, priority DESC)
            WHERE status = 'pending'
        """)

        # Seen cache - tracks recently seen messages for deduplication
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_cache (
                message_id TEXT PRIMARY KEY,        -- Message ID
                fragment_idx INTEGER,               -- Fragment index if fragment
                seen_at INTEGER NOT NULL,           -- Unix timestamp when seen
                rebroadcast INTEGER DEFAULT 0       -- Whether we rebroadcast it
            )
        """)

        # Create index for seen cache cleanup
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_seen_cache_cleanup
            ON seen_cache(seen_at)
        """)

    # Message operations
    async def save_message(self, message: Dict[str, Any]) -> bool:
        """
        Save a message to the database.

        Args:
            message: Message data dictionary

        Returns:
            True if saved (new), False if duplicate
        """
        try:
            await self.conn.execute("""
                INSERT INTO messages (
                    id, from_node, author, timestamp, channel, priority,
                    reply_to, body, received_at, raw_frame
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message['id'],
                message['from_node'],
                message.get('author'),
                message['timestamp'],
                message['channel'],
                message['priority'],
                message.get('reply_to'),
                message['body'],
                int(datetime.utcnow().timestamp()),
                message.get('raw_frame', '')
            ))
            await self.conn.commit()

            # Update channel stats
            await self._update_channel_stats(message['channel'], message['from_node'])

            # Update node stats
            await self._update_node_stats(message['from_node'], 'message')

            return True
        except aiosqlite.IntegrityError:
            # Duplicate message ID
            return False

    async def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get a message by ID."""
        async with self.conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_recent_messages(self,
                                   limit: int = 100,
                                   channel: Optional[str] = None,
                                   from_node: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent messages with optional filtering."""
        query = "SELECT * FROM messages WHERE 1=1"
        params = []

        if channel:
            query += " AND channel = ?"
            params.append(channel)

        if from_node:
            query += " AND from_node = ?"
            params.append(from_node)

        query += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)

        async with self.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Fragment operations
    async def save_fragment(self, fragment: Dict[str, Any]) -> bool:
        """Save a message fragment."""
        try:
            await self.conn.execute("""
                INSERT INTO fragments (message_id, idx, total, data, received_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                fragment['message_id'],
                fragment['idx'],
                fragment['total'],
                fragment['data'],
                int(datetime.utcnow().timestamp())
            ))
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            # Duplicate fragment
            return False

    async def get_fragments(self, message_id: str) -> List[Dict[str, Any]]:
        """Get all fragments for a message."""
        async with self.conn.execute(
            "SELECT * FROM fragments WHERE message_id = ? ORDER BY idx",
            (message_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def cleanup_old_fragments(self, max_age_seconds: int = 3600):
        """Remove old incomplete fragments."""
        cutoff = int((datetime.utcnow() - timedelta(seconds=max_age_seconds)).timestamp())

        await self.conn.execute(
            "DELETE FROM fragments WHERE received_at < ?",
            (cutoff,)
        )
        await self.conn.commit()

    # Node operations
    async def _update_node_stats(self, callsign: str, activity_type: str):
        """Update node statistics."""
        now = int(datetime.utcnow().timestamp())

        if activity_type == 'message':
            await self.conn.execute("""
                INSERT INTO nodes (callsign, first_seen, last_seen, message_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(callsign) DO UPDATE SET
                    last_seen = ?,
                    message_count = message_count + 1
            """, (callsign, now, now, now))
        elif activity_type == 'sync':
            await self.conn.execute("""
                INSERT INTO nodes (callsign, first_seen, last_seen, last_sync, sync_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(callsign) DO UPDATE SET
                    last_seen = ?,
                    last_sync = ?,
                    sync_count = sync_count + 1
            """, (callsign, now, now, now, now, now))
        elif activity_type == 'req':
            await self.conn.execute("""
                INSERT INTO nodes (callsign, first_seen, last_seen, req_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(callsign) DO UPDATE SET
                    last_seen = ?,
                    req_count = req_count + 1
            """, (callsign, now, now, now))

    async def _update_user_stats(self, username: str, activity_type: str):
        """Update user statistics keyed by application-level nickname."""
        if not username:
            return

        now = int(datetime.utcnow().timestamp())

        if activity_type == 'message':
            await self.conn.execute("""
                INSERT INTO users (username, first_seen, last_seen, message_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(username) DO UPDATE SET
                    last_seen = ?,
                    message_count = message_count + 1
            """, (username, now, now, now))
            await self.conn.commit()

    async def get_active_nodes(self, since_seconds: int = 3600) -> List[Dict[str, Any]]:
        """Get recently active nodes."""
        cutoff = int((datetime.utcnow() - timedelta(seconds=since_seconds)).timestamp())

        async with self.conn.execute(
            "SELECT * FROM nodes WHERE last_seen > ? ORDER BY last_seen DESC",
            (cutoff,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Channel operations
    async def _update_channel_stats(self, channel: str, from_node: str):
        """Update channel statistics."""
        now = int(datetime.utcnow().timestamp())

        await self.conn.execute("""
            INSERT INTO channels (name, first_message, last_message, message_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                last_message = ?,
                message_count = message_count + 1
        """, (channel, now, now, now))

    async def get_channels(self) -> List[Dict[str, Any]]:
        """Get all known channels with stats."""
        async with self.conn.execute(
            "SELECT * FROM channels ORDER BY last_message DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Request tracking
    async def track_request(self, message_id: str) -> Dict[str, Any]:
        """Track a REQ for rate limiting."""
        now = int(datetime.utcnow().timestamp())

        async with self.conn.execute(
            "SELECT * FROM request_tracking WHERE message_id = ?",
            (message_id,)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            # Update existing request
            retry_count = existing['retry_count'] + 1
            backoff = min(600, existing['backoff_seconds'] * 2)  # Exponential backoff

            await self.conn.execute("""
                UPDATE request_tracking SET
                    last_request = ?,
                    retry_count = ?,
                    backoff_seconds = ?
                WHERE message_id = ?
            """, (now, retry_count, backoff, message_id))
        else:
            # New request
            await self.conn.execute("""
                INSERT INTO request_tracking
                (message_id, first_request, last_request, retry_count, backoff_seconds)
                VALUES (?, ?, ?, 0, 30)
            """, (message_id, now, now))

        await self.conn.commit()

        async with self.conn.execute(
            "SELECT * FROM request_tracking WHERE message_id = ?",
            (message_id,)
        ) as cursor:
            return dict(await cursor.fetchone())

    async def can_request(self, message_id: str) -> bool:
        """Check if we can send a REQ for this message."""
        async with self.conn.execute(
            "SELECT * FROM request_tracking WHERE message_id = ?",
            (message_id,)
        ) as cursor:
            tracker = await cursor.fetchone()

        if not tracker:
            return True  # First request

        if tracker['success']:
            return False  # Already received

        if tracker['retry_count'] >= 4:
            return False  # Max retries reached

        # Check backoff period
        now = int(datetime.utcnow().timestamp())
        next_allowed = tracker['last_request'] + tracker['backoff_seconds']

        return now >= next_allowed

    async def get_recent_requests(self, window_seconds: int = 60) -> int:
        """Count recent REQ frames for rate limiting."""
        cutoff = int((datetime.utcnow() - timedelta(seconds=window_seconds)).timestamp())

        async with self.conn.execute(
            "SELECT COUNT(*) as count FROM request_tracking WHERE last_request > ?",
            (cutoff,)
        ) as cursor:
            result = await cursor.fetchone()
            return result['count']

    # Transmission queue
    async def queue_transmission(self, frame_type: str, frame_data: str,
                                  priority: int = 1, delay_seconds: float = 0):
        """Queue a frame for transmission."""
        now = int(datetime.utcnow().timestamp())
        scheduled = now + int(delay_seconds)

        await self.conn.execute("""
            INSERT INTO transmission_queue
            (frame_type, frame_data, priority, scheduled_at, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (frame_type, frame_data, priority, scheduled, now))
        await self.conn.commit()

    async def get_next_transmission(self) -> Optional[Dict[str, Any]]:
        """Get the next frame to transmit."""
        now = int(datetime.utcnow().timestamp())

        async with self.conn.execute("""
            SELECT * FROM transmission_queue
            WHERE status = 'pending' AND scheduled_at <= ?
            ORDER BY priority DESC, scheduled_at ASC
            LIMIT 1
        """, (now,)) as cursor:
            row = await cursor.fetchone()
            if row:
                # Mark as transmitting
                await self.conn.execute(
                    "UPDATE transmission_queue SET status = 'transmitting' WHERE id = ?",
                    (row['id'],)
                )
                await self.conn.commit()
                return dict(row)
        return None

    # Seen cache for deduplication
    async def is_seen(self, message_id: str, fragment_idx: Optional[int] = None,
                      rebroadcast: bool = False) -> bool:
        """Check if we've seen this message/fragment recently."""
        if fragment_idx is not None:
            async with self.conn.execute(
                "SELECT 1 FROM seen_cache WHERE message_id = ? AND fragment_idx = ?",
                (message_id, fragment_idx)
            ) as cursor:
                return await cursor.fetchone() is not None
        elif rebroadcast:
            # Check if already marked for rebroadcast
            async with self.conn.execute(
                "SELECT 1 FROM seen_cache WHERE message_id = ? AND fragment_idx IS NULL AND rebroadcast = 1",
                (message_id,)
            ) as cursor:
                return await cursor.fetchone() is not None
        else:
            async with self.conn.execute(
                "SELECT 1 FROM seen_cache WHERE message_id = ? AND fragment_idx IS NULL",
                (message_id,)
            ) as cursor:
                return await cursor.fetchone() is not None

    async def mark_seen(self, message_id: str, fragment_idx: Optional[int] = None,
                        rebroadcast: bool = False):
        """Mark a message/fragment as seen."""
        now = int(datetime.utcnow().timestamp())

        await self.conn.execute("""
            INSERT OR REPLACE INTO seen_cache (message_id, fragment_idx, seen_at, rebroadcast)
            VALUES (?, ?, ?, ?)
        """, (message_id, fragment_idx, now, int(rebroadcast)))
        await self.conn.commit()

    async def mark_seen_if_new(self, message_id: str, fragment_idx: Optional[int] = None) -> bool:
        """
        Atomically check if message is new and mark it as seen.
        Returns True if the message was new (and is now marked seen).
        Returns False if the message was already seen.
        This avoids the race condition between is_seen() and mark_seen().
        """
        now = int(datetime.utcnow().timestamp())

        # INSERT OR IGNORE will only insert if the unique constraint isn't violated
        # We can check rowcount to see if insert happened
        if fragment_idx is not None:
            cursor = await self.conn.execute("""
                INSERT OR IGNORE INTO seen_cache (message_id, fragment_idx, seen_at, rebroadcast)
                VALUES (?, ?, ?, 0)
            """, (message_id, fragment_idx, now))
        else:
            cursor = await self.conn.execute("""
                INSERT OR IGNORE INTO seen_cache (message_id, fragment_idx, seen_at, rebroadcast)
                VALUES (?, NULL, ?, 0)
            """, (message_id, now))

        await self.conn.commit()
        # rowcount > 0 means insert succeeded (message was new)
        return cursor.rowcount > 0

    async def cleanup_seen_cache(self, max_age_seconds: int = 3600):
        """Remove old entries from seen cache."""
        cutoff = int((datetime.utcnow() - timedelta(seconds=max_age_seconds)).timestamp())

        await self.conn.execute(
            "DELETE FROM seen_cache WHERE seen_at < ?",
            (cutoff,)
        )
        await self.conn.commit()