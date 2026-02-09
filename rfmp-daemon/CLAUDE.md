# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RFMP Daemon is a Python implementation of the RF Microblog Protocol v0.3 - a decentralized, append-only microblogging protocol for packet radio networks using AX.25 UI frames. It connects to Direwolf TNC via TCP KISS for radio communication.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e .

# Run daemon
python -m rfmpd.main -c config.yaml
python -m rfmpd.main -c config.yaml -v  # verbose mode

# After pip install -e ., can also use:
rfmpd -c config.yaml

# Testing
pytest tests/

# Code formatting
black rfmpd/ tests/

# Type checking
mypy rfmpd/
```

## Architecture

**Layered async architecture with these main components:**

- **RFMPDaemon (main.py)** - Central orchestrator managing background loops (sync, cleanup, transmission), message routing, and WebSocket clients

- **API Layer (api/)** - FastAPI REST endpoints on port 8080:
  - `/messages` - CRUD operations
  - `/nodes`, `/channels` - Network statistics
  - `/status` - Daemon health
  - `/stream` - WebSocket for real-time updates

- **Network Layer (network/)** - Radio communication:
  - `direwolf.py` - TNC connection via TCP KISS with auto-reconnect
  - `ax25.py` - Frame parsing/generation
  - `kiss.py` - KISS protocol

- **Protocol Layer (protocol/)** - RFMP v0.3:
  - 4 frame types: MSG, FRAG, SYNC, REQ
  - Message IDs: 8-12 char hex from SHA256(sender + timestamp + body)
  - Automatic fragmentation for messages >200 bytes

- **Storage Layer (storage/)** - SQLite via aiosqlite:
  - `messages`, `fragments`, `nodes`, `channels`, `users` tables
  - `transmission_queue` for outbound frames
  - `seen_cache` for deduplication
  - `bloom_windows` for sync state

- **Sync Layer (sync/)** - Synchronization:
  - Rotating Bloom filters (3 windows × 600s)
  - Adaptive timing with priority-based delays
  - Rate limiting (max 6 REQ/min with exponential backoff)

## Key Concepts

- **Author vs Callsign**: Messages have an `author` field (application-level nickname) separate from the node's radio callsign, allowing multiple users per physical node

- **Offline Mode**: Set `network.offline_mode: true` in config for testing without Direwolf/radio hardware

- **Configuration**: YAML config validated by Pydantic. Environment variables supported via `RFMPD_` prefix (e.g., `RFMPD_NODE__CALLSIGN`)
