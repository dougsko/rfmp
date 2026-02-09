#!/bin/bash
# RFMP Daemon Installation Script

set -e

echo "RFMP Daemon Installation Script"
echo "================================"
echo

# Check if running on Raspberry Pi or Linux
if [ ! -f /etc/os-release ]; then
    echo "Error: This script requires a Linux system"
    exit 1
fi

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -Po '(?<=Python )\d+\.\d+')
REQUIRED_VERSION="3.9"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Error: Python 3.9+ is required, found Python $PYTHON_VERSION"
    exit 1
fi
echo "✓ Python $PYTHON_VERSION found"

# Create virtual environment
echo "Creating Python virtual environment..."
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    python3 -m venv "$SCRIPT_DIR/venv"
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✓ pip upgraded"

# Install dependencies
echo "Installing Python dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" > /dev/null 2>&1
echo "✓ Dependencies installed"

# Install package in development mode
echo "Installing RFMP daemon package..."
pip install -e "$SCRIPT_DIR" > /dev/null 2>&1
echo "✓ Package installed"

# Create configuration directory
echo "Creating configuration directory..."
mkdir -p ~/rfmpd
echo "✓ Configuration directory created at ~/rfmpd"

# Copy example configuration if it doesn't exist
if [ ! -f ~/rfmpd/config.yaml ]; then
    echo "Copying example configuration..."
    cp "$SCRIPT_DIR/config.yaml.example" ~/rfmpd/config.yaml
    echo "✓ Configuration file created at ~/rfmpd/config.yaml"
    echo
    echo "IMPORTANT: Edit ~/rfmpd/config.yaml and set your callsign!"
else
    echo "✓ Configuration file already exists at ~/rfmpd/config.yaml"
fi

# Ask about systemd service installation
echo
read -p "Do you want to install the systemd service? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing systemd service..."

    # Update service file with correct paths
    sed "s|/home/pi/IdeaProjects/rfmp-daemon|$SCRIPT_DIR|g" "$SCRIPT_DIR/rfmpd.service" > /tmp/rfmpd.service
    sed -i "s|User=pi|User=$USER|g" /tmp/rfmpd.service
    sed -i "s|Group=pi|Group=$USER|g" /tmp/rfmpd.service
    sed -i "s|/home/pi/rfmpd|$HOME/rfmpd|g" /tmp/rfmpd.service

    # Install service
    sudo cp /tmp/rfmpd.service /etc/systemd/system/
    sudo systemctl daemon-reload
    echo "✓ Systemd service installed"

    echo
    echo "To enable auto-start on boot:"
    echo "  sudo systemctl enable rfmpd"
    echo
    echo "To start the daemon now:"
    echo "  sudo systemctl start rfmpd"
    echo
    echo "To check daemon status:"
    echo "  sudo systemctl status rfmpd"
    echo
    echo "To view logs:"
    echo "  journalctl -u rfmpd -f"
fi

echo
echo "Installation complete!"
echo
echo "Next steps:"
echo "1. Edit configuration: nano ~/rfmpd/config.yaml"
echo "2. Set your callsign in the configuration"
echo "3. Configure Direwolf if not already done"
echo "4. Start the daemon:"
echo "   - With systemd: sudo systemctl start rfmpd"
echo "   - Manually: $SCRIPT_DIR/venv/bin/python -m rfmpd.main"
echo
echo "API will be available at: http://localhost:8080"
echo "API documentation: http://localhost:8080/docs"