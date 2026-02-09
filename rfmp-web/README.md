# RFMP Web UI

A collection of web interfaces for the RFMP (RF Microblog Protocol) daemon.

## Available UIs

### Twitter UI (`web-ui-twitter/`)
A modern, Twitter-like microblogging interface optimized for mobile devices.

**Features:**
- 📱 Mobile-first responsive design
- 🌓 Dark/Light theme toggle
- 💬 Real-time message updates via WebSocket
- #️⃣ Channel switching (general, ops, weather)
- 💭 Reply to messages with threading
- 🎯 Message priority levels
- 👤 Simple username selection (no auth)
- 📊 Live network statistics

## Installation

### Prerequisites
- Python 3.9+
- RFMP daemon running (default: http://localhost:8080)

### Setup

1. **Clone or navigate to the repository:**
```bash
cd ~/IdeaProjects/rfmp-web
```

2. **Create a virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

## Running the Web UI

### Quick Start (Twitter UI)

```bash
# From the rfmp-web directory
cd web-ui-twitter
python server.py
```

The UI will be available at: http://localhost:3000

### Command Line Options

```bash
python server.py --help

Options:
  --host HOST           Host to bind to (default: 0.0.0.0)
  --port PORT           Port to listen on (default: 3000)
  --api-url API_URL     RFMP daemon API URL (default: http://localhost:8080)
  --debug               Run in debug mode
```

### Examples

```bash
# Run on a different port
python server.py --port 5000

# Connect to remote RFMP daemon
python server.py --api-url http://192.168.1.100:8080

# Run in debug mode for development
python server.py --debug
```

## Usage

1. **First Visit:**
   - Enter your display name (no authentication required)
   - This name is saved locally in your browser

2. **Posting Messages:**
   - Type your message (up to 500 characters)
   - Select priority level (Urgent/Normal/Low/Minimal)
   - Press Send or use Ctrl+Enter (Cmd+Enter on Mac)

3. **Channels:**
   - Click on channel names in the sidebar to switch
   - Each channel shows its message count
   - Common channels: general, ops, weather

4. **Replying:**
   - Click Reply on any message to create a thread
   - Reply-to information is included with your message

5. **Theme:**
   - Click the moon/sun icon to toggle dark/light mode
   - Your preference is saved locally

## Mobile Experience

The UI is optimized for mobile devices:
- Tap the hamburger menu to access channels and stats
- Swipe or tap outside to close the sidebar
- Pull down to refresh messages
- Responsive layout adapts to screen size

## Architecture

```
rfmp-web/
├── web-ui-twitter/          # Twitter-like UI
│   ├── server.py           # Flask web server
│   ├── templates/
│   │   └── index.html      # Main HTML template
│   └── static/
│       ├── css/
│       │   └── style.css   # Responsive styles with themes
│       └── js/
│           └── app.js      # Vanilla JavaScript application
└── [future-ui]/            # Space for additional UIs
```

## Adding New UIs

The structure is designed to support multiple UIs. To add a new UI:

1. Create a new directory: `web-ui-yourname/`
2. Add a `server.py` based on the Twitter UI example
3. Implement your custom templates and static files
4. Update this README with the new UI documentation

## API Endpoints Used

The web UI interacts with these RFMP daemon endpoints:

- `GET /messages` - Fetch messages
- `POST /messages` - Send new message
- `GET /channels` - List channels
- `GET /nodes` - List active nodes
- `GET /status` - Get daemon status
- `WS /stream` - WebSocket for real-time updates

## Browser Support

- ✅ Chrome/Edge (latest)
- ✅ Firefox (latest)
- ✅ Safari (latest)
- ✅ Mobile Safari (iOS)
- ✅ Chrome Mobile (Android)

## Development

### Project Structure
- **No build step required** - Uses vanilla JavaScript
- **No framework dependencies** - Easy to modify
- **Mobile-first CSS** - Responsive by default
- **WebSocket support** - Real-time updates

### Customization

#### Changing Colors
Edit the CSS variables in `static/css/style.css`:
```css
:root {
    --accent-color: #1d9bf0;  /* Change primary color */
    --bg-primary: #ffffff;     /* Change background */
}
```

#### Adding Channels
Add new channel buttons in `index.html`:
```html
<button class="channel-btn" data-channel="yourchann">
    <i class="fas fa-hashtag"></i>
    <span>yourchann</span>
</button>
```

## Troubleshooting

### Cannot connect to RFMP daemon
- Ensure the daemon is running: `sudo systemctl status rfmpd`
- Check the API URL: `--api-url http://localhost:8080`
- Verify CORS is enabled in the daemon configuration

### WebSocket connection fails
- Check if the daemon supports WebSocket on `/stream`
- Ensure firewall allows WebSocket connections
- Try refreshing the page

### Messages not appearing
- Check browser console for errors (F12)
- Verify the channel exists in the daemon
- Ensure you have network connectivity

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Feel free to:
- Submit bug reports
- Propose new features
- Create additional UI themes
- Develop alternative UIs

## Support

For issues related to:
- **Web UI**: Create an issue in this repository
- **RFMP Daemon**: Check the rfmp-daemon repository
- **Protocol**: Refer to RFMP specification v0.3