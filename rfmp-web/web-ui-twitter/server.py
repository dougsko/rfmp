#!/usr/bin/env python3
"""
Twitter-like Web UI Server for RFMP Daemon
A mobile-first microblogging interface

This server proxies all API and WebSocket requests to the RFMP daemon,
allowing remote clients to connect without hardcoded URLs.
"""

import os
import logging
from pathlib import Path
from flask import Flask, render_template, send_from_directory, request, Response
from flask_cors import CORS
from flask_sock import Sock
import requests
import websocket

# Try to import gevent for production mode
try:
    import gevent
    from gevent import spawn
    HAS_GEVENT = True
except ImportError:
    HAS_GEVENT = False
    import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app(api_url="http://localhost:8080"):
    """Create Flask application for serving the web UI."""

    # Get the directory where this script is located
    base_dir = Path(__file__).parent

    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static")
    )

    # Enable CORS
    CORS(app)

    # Initialize WebSocket support
    sock = Sock(app)

    # Store API URL for proxying
    app.config['RFMP_API_URL'] = api_url
    app.config['RFMP_WS_URL'] = api_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/stream'

    def proxy_request(path):
        """Proxy an HTTP request to the RFMP daemon."""
        url = f"{app.config['RFMP_API_URL']}{path}"

        # Forward query parameters
        if request.query_string:
            url = f"{url}?{request.query_string.decode('utf-8')}"

        # Get request body for POST/PUT
        data = None
        json_data = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            if request.is_json:
                json_data = request.get_json(silent=True)
            else:
                data = request.get_data()

        # Forward headers (excluding hop-by-hop headers)
        excluded_headers = {'host', 'connection', 'keep-alive', 'transfer-encoding',
                          'te', 'trailer', 'upgrade', 'proxy-authorization',
                          'proxy-authenticate'}
        headers = {k: v for k, v in request.headers if k.lower() not in excluded_headers}

        try:
            resp = requests.request(
                method=request.method,
                url=url,
                json=json_data,
                data=data if not json_data else None,
                headers=headers,
                timeout=30
            )

            # Forward response
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get('content-type', 'application/json')
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Proxy error: {e}")
            return Response(
                f'{{"error": "Failed to connect to RFMP daemon: {str(e)}"}}',
                status=502,
                content_type='application/json'
            )

    @app.route('/')
    def index():
        """Serve the main application."""
        return render_template('index.html', api_url=app.config['RFMP_API_URL'])

    @app.route('/health')
    def health():
        """Health check endpoint."""
        return {'status': 'healthy', 'api_url': app.config['RFMP_API_URL']}

    # ===== API Proxy Routes =====

    @app.route('/messages', methods=['GET', 'POST'])
    def proxy_messages():
        """Proxy messages endpoint."""
        return proxy_request('/messages')

    @app.route('/messages/<path:message_id>', methods=['GET'])
    def proxy_message_by_id(message_id):
        """Proxy single message endpoint."""
        return proxy_request(f'/messages/{message_id}')

    @app.route('/channels', methods=['GET', 'POST'])
    def proxy_channels():
        """Proxy channels endpoint."""
        return proxy_request('/channels')

    @app.route('/nodes', methods=['GET'])
    def proxy_nodes():
        """Proxy nodes endpoint."""
        return proxy_request('/nodes')

    @app.route('/status', methods=['GET'])
    def proxy_status():
        """Proxy status endpoint."""
        return proxy_request('/status')

    @app.route('/config/callsign', methods=['GET'])
    def proxy_callsign():
        """Proxy callsign config endpoint."""
        return proxy_request('/config/callsign')

    # ===== WebSocket Proxy =====

    @sock.route('/stream')
    def stream_proxy(ws):
        """Proxy WebSocket connection to RFMP daemon."""
        daemon_ws = None

        try:
            # Connect to daemon WebSocket
            daemon_ws = websocket.create_connection(app.config['RFMP_WS_URL'])
            daemon_ws.settimeout(0.1)  # Short timeout for polling
            logger.info("WebSocket proxy connected to daemon")

            # Single-threaded polling loop - check both directions
            while True:
                # Check for messages from daemon -> forward to browser
                try:
                    msg = daemon_ws.recv()
                    if msg:
                        ws.send(msg)
                except websocket.WebSocketTimeoutException:
                    pass  # No message from daemon, continue

                # Check for messages from browser -> forward to daemon
                try:
                    msg = ws.receive(timeout=0.1)
                    if msg is None:
                        continue  # Timeout, no message
                    daemon_ws.send(msg)
                except Exception as e:
                    if 'timed out' in str(e).lower():
                        continue  # Timeout, no message
                    logger.info(f"Browser disconnected: {e}")
                    break

        except Exception as e:
            logger.error(f"WebSocket proxy error: {e}")
        finally:
            if daemon_ws:
                try:
                    daemon_ws.close()
                except:
                    pass
            logger.info("WebSocket proxy disconnected")

    # ===== Static Files =====

    @app.route('/static/<path:path>')
    def send_static(path):
        return send_from_directory('static', path)

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(
            str(base_dir / "static" / "images"),
            'favicon.ico',
            mimetype='image/x-icon'
        )

    return app


def main():
    """Run the web UI server."""
    import argparse

    parser = argparse.ArgumentParser(description='RFMP Web UI Server')
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=3000,
        help='Port to listen on (default: 3000)'
    )
    parser.add_argument(
        '--api-url',
        default='http://localhost:8080',
        help='RFMP daemon API URL (default: http://localhost:8080)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Run in debug mode'
    )

    args = parser.parse_args()

    # Create and run app
    app = create_app(api_url=args.api_url)

    logger.info(f"Starting RFMP Web UI Server")
    logger.info(f"Listening on http://{args.host}:{args.port}")
    logger.info(f"Proxying to RFMP daemon at {args.api_url}")

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug
    )


if __name__ == '__main__':
    main()
