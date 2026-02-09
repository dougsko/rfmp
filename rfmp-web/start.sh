#!/bin/bash
# RFMP Web UI Startup Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${GREEN}RFMP Web UI Launcher${NC}"
echo "===================="
echo

# Check if virtual environment exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv "$SCRIPT_DIR/venv"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Check if dependencies are installed
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -q -r "$SCRIPT_DIR/requirements.txt"
    echo -e "${GREEN}✓ Dependencies installed${NC}"
fi

# Check if gunicorn and gevent are installed (for production mode with WebSocket support)
if ! python -c "import gunicorn; import gevent" 2>/dev/null; then
    echo -e "${YELLOW}Installing gunicorn + gevent for production server...${NC}"
    pip install -q gunicorn gevent gevent-websocket
    echo -e "${GREEN}✓ gunicorn + gevent installed${NC}"
fi

# Parse arguments (use environment variables as defaults)
UI_DIR="${RFMP_UI:-web-ui-twitter}"
API_URL="${RFMP_API_URL:-http://localhost:8080}"
PORT="${RFMP_PORT:-3000}"
DEBUG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --ui)
            UI_DIR="$2"
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo
            echo "Options:"
            echo "  --ui DIR         UI directory to use (default: \$RFMP_UI or web-ui-twitter)"
            echo "  --api-url URL    RFMP daemon API URL (default: \$RFMP_API_URL or http://localhost:8080)"
            echo "  --port PORT      Port to listen on (default: \$RFMP_PORT or 3000)"
            echo "  --debug          Run in debug mode (uses Flask dev server)"
            echo "  --help           Show this help message"
            echo
            echo "Environment variables:"
            echo "  RFMP_UI          Default UI directory"
            echo "  RFMP_API_URL     Default RFMP daemon API URL"
            echo "  RFMP_PORT        Default port to listen on"
            echo
            echo "Available UIs:"
            for dir in "$SCRIPT_DIR"/web-ui-*/; do
                if [ -d "$dir" ]; then
                    basename "$dir"
                fi
            done
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check if UI directory exists
if [ ! -d "$SCRIPT_DIR/$UI_DIR" ]; then
    echo -e "${RED}Error: UI directory '$UI_DIR' not found${NC}"
    echo "Available UIs:"
    for dir in "$SCRIPT_DIR"/web-ui-*/; do
        if [ -d "$dir" ]; then
            echo "  - $(basename "$dir")"
        fi
    done
    exit 1
fi

# Check if RFMP daemon is accessible
echo -e "Checking RFMP daemon at ${YELLOW}$API_URL${NC}..."
if curl -s -f -o /dev/null "$API_URL/health" 2>/dev/null; then
    echo -e "${GREEN}✓ RFMP daemon is accessible${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Cannot reach RFMP daemon at $API_URL${NC}"
    echo "  The web UI will start but may not function properly."
    echo "  Ensure the RFMP daemon is running and accessible."
fi

echo
echo -e "${GREEN}Starting $UI_DIR...${NC}"
echo "------------------------"
echo -e "Web UI: ${YELLOW}http://0.0.0.0:$PORT${NC}"
echo -e "API URL: ${YELLOW}$API_URL${NC}"
echo
echo "Press Ctrl+C to stop"
echo

# Start the server
cd "$SCRIPT_DIR/$UI_DIR"
export RFMP_API_URL="$API_URL"

if [ -n "$DEBUG" ]; then
    # Debug mode: use Flask dev server
    echo -e "${YELLOW}Running in debug mode (Flask dev server)${NC}"
    python server.py --port "$PORT" --api-url "$API_URL" --debug
else
    # Production mode: use gunicorn with gevent for WebSocket support
    gunicorn --bind "0.0.0.0:$PORT" --worker-class gevent --workers 1 "server:create_app('$API_URL')"
fi