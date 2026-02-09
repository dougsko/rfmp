# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RFMP Web UI - A Flask-based web frontend for the RFMP (RF Microblog Protocol) daemon. Currently implements a Twitter-like interface (`web-ui-twitter/`). Uses vanilla JavaScript with no build step.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run (from project root)
./start.sh
./start.sh --ui web-ui-twitter --api-url http://localhost:8080 --port 3000 --debug

# Or directly
cd web-ui-twitter && python server.py --debug
```

## Architecture

```
rfmp-web/
├── web-ui-twitter/           # Self-contained UI implementation
│   ├── server.py            # Flask server - proxies API/WS to daemon
│   ├── templates/index.html # Single-page app template (Jinja2)
│   └── static/
│       ├── css/style.css    # Mobile-first CSS with theme variables
│       └── js/app.js        # Vanilla JS SPA (~1000 lines)
└── start.sh                 # Launcher with venv/deps auto-setup
```

**Communication Flow:**
- Browser ← HTTP/WS → Flask (port 3000) ← proxy → RFMP Daemon (port 8080)
- All requests go through Flask proxy, enabling remote access from any machine

**Proxied Endpoints:**
- `GET/POST /messages`, `GET /messages/<id>`, `GET/POST /channels`
- `GET /nodes`, `GET /status`, `GET /config/callsign`
- `WS /stream` - Real-time message updates (bidirectional proxy)

## Key Patterns

**JavaScript State (app.js):**
```javascript
const app = {
    config: {...},       // API URL, WebSocket URL
    state: {...},        // Current channel, messages, nodes
    ws: null,           // WebSocket connection
    pendingMessages: {} // Optimistic UI tracking (temp ID → message)
}
```

**Theming:** CSS custom properties in `:root` (style.css). Dark/light toggle persisted to localStorage.

**Optimistic Updates:** Messages rendered immediately with temp IDs, reconciled when server confirms.

**HTML Escaping:** All user content goes through `escapeHtml()` before rendering.

## Adding New UIs

Create `web-ui-yourname/` with same structure as `web-ui-twitter/`. The launcher script auto-discovers UIs matching `web-ui-*/`.
