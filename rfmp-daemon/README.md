# RFMP Daemon

RF Microblog Protocol (RFMP) v0.3 daemon implementation for packet radio networks.

## Overview

RFMP is a decentralized, append-only microblogging and coordination protocol designed for unreliable packet radio networks using AX.25 UI frames. This daemon provides:

- Full RFMP v0.3 protocol implementation
- REST API for web interface integration
- SQLite-based persistent message storage
- Automatic synchronization using rotating Bloom filters
- Adaptive timing for collision reduction
- Message fragmentation for large payloads

## Installation

### Prerequisites

- Raspberry Pi with Python 3.9+
- Direwolf TNC software (for packet radio interface)
- Amateur radio license (for transmission)

### Setup

1. Clone the repository:
```bash
cd ~/IdeaProjects
git clone https://github.com/yourusername/rfmp-daemon.git
cd rfmp-daemon
```

2. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

4. Configure the daemon:
```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your callsign and settings
```

5. Set up systemd service (optional):
```bash
sudo cp rfmpd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rfmpd
sudo systemctl start rfmpd
```

## Configuration

Edit `config.yaml` to configure:

- **Node**: Your callsign and SSID
- **Network**: Direwolf connection settings
- **Storage**: Database location
- **API**: REST API port and host

## API Documentation

The daemon provides a REST API on port 8080 (configurable):

### Endpoints

- `GET /messages` - List messages with optional filtering
- `GET /messages/{id}` - Get specific message
- `POST /messages` - Send new message
- `GET /channels` - List active channels
- `GET /nodes` - List seen nodes
- `GET /status` - Daemon status and statistics
- `WS /stream` - WebSocket for real-time updates

### Example Usage

```bash
# Send a message
curl -X POST http://localhost:8080/messages \
  -H "Content-Type: application/json" \
  -d '{"channel": "general", "body": "Hello RFMP!", "priority": 1}'

# Get recent messages
curl http://localhost:8080/messages?channel=general&limit=10
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black rfmpd/ tests/
```

### Type Checking

```bash
mypy rfmpd/
```

## Protocol Details

RFMP v0.3 implements:

- **Frame Types**: MSG, FRAG, SYNC, REQ
- **Message IDs**: Content-derived 8-12 character hex strings
- **Synchronization**: Rotating Bloom filters (3x 600s windows)
- **Fragmentation**: Automatic for messages >200 bytes
- **Adaptive Timing**: Priority-based transmission delays
- **Rate Limiting**: Max 6 REQ/min with exponential backoff

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please read CONTRIBUTING.md for guidelines.

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/rfmp-daemon/issues
- Amateur Radio: Monitor channel "general" on local packet frequencies