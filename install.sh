#!/usr/bin/env bash
set -euo pipefail

# install.sh [target_user]
# Copies repo to /home/<target_user>/rfmp, installs systemd units and udev rules,
# sets permissions, reloads systemd/udev, and enables the main services.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"

TARGET_USER="${1:-}${SUDO_USER:-}"
if [ -z "$TARGET_USER" ]; then
  TARGET_USER="orangepi"
fi
TARGET_HOME="/home/$TARGET_USER"
TARGET_DIR="$TARGET_HOME/rfmp"

echo "Installing RFMP to $TARGET_DIR as user $TARGET_USER"

if [ "$EUID" -ne 0 ]; then
  echo "This installer must be run with sudo/root." >&2
  echo "Usage: sudo $0 [target_user]" >&2
  exit 1
fi

# copy code (exclude git metadata)
mkdir -p "$TARGET_DIR"
rsync -a --delete --exclude '.git' --exclude '__pycache__' "$REPO_DIR/" "$TARGET_DIR/"

# ensure the target user exists (best-effort)
if ! id -u "$TARGET_USER" >/dev/null 2>&1; then
  echo "Warning: user '$TARGET_USER' does not exist. Files will be owned by root." >&2
  CHOWN_ARGS="-R root:root"
else
  CHOWN_ARGS="-R $TARGET_USER:$TARGET_USER"
fi

chown $CHOWN_ARGS "$TARGET_DIR"

# make launchers executable
if [ -f "$TARGET_DIR/rfmp-daemon/start.sh" ]; then
  chmod +x "$TARGET_DIR/rfmp-daemon/start.sh"
fi
if [ -f "$TARGET_DIR/rfmp-web/start.sh" ]; then
  chmod +x "$TARGET_DIR/rfmp-web/start.sh"
fi
if [ -f "$TARGET_DIR/direwolf-wrapper.sh" ]; then
  chmod +x "$TARGET_DIR/direwolf-wrapper.sh"
fi

# install systemd units
SYSTEMD_DIR=/etc/systemd/system
for unit in rfmp-daemon.service rfmp-web.service direwolf@.service; do
  if [ -f "$TARGET_DIR/$unit" ]; then
    sudo cp "$TARGET_DIR/$unit" "$SYSTEMD_DIR/"

    # ensure unit runs as the target user and has HOME set
    if grep -q "^\[Service\]" "$SYSTEMD_DIR/$unit"; then
      if ! grep -q "^User=" "$SYSTEMD_DIR/$unit"; then
        sed -i "/^\[Service\]/a User=$TARGET_USER\nEnvironment=HOME=$TARGET_HOME" "$SYSTEMD_DIR/$unit"
      else
        # replace existing User/Environment lines if present
        sed -i "s/^User=.*/User=$TARGET_USER/" "$SYSTEMD_DIR/$unit" || true
        if grep -q "^Environment=.*HOME=" "$SYSTEMD_DIR/$unit"; then
          sed -i "s|^Environment=.*HOME=.*|Environment=HOME=$TARGET_HOME|" "$SYSTEMD_DIR/$unit" || true
        else
          sed -i "/^User=.*/a Environment=HOME=$TARGET_HOME" "$SYSTEMD_DIR/$unit"
        fi
      fi
    fi
  fi
done

# install udev rule if present
if [ -f "$TARGET_DIR/99-ptt.rules" ]; then
  sudo cp "$TARGET_DIR/99-ptt.rules" /etc/udev/rules.d/99-ptt.rules
fi

echo "Reloading udev and systemd..."
udevadm control --reload-rules || true
udevadm trigger || true
systemctl daemon-reload

echo "Enabling and starting services: rfmp-daemon, rfmp-web"
systemctl enable --now rfmp-daemon.service || true
systemctl enable --now rfmp-web.service || true

echo
echo "If you want to enable Direwolf instances (digirig,qmx,digilite), run:"
echo "  sudo systemctl enable --now direwolf@digirig.service direwolf@qmx.service direwolf@digilite.service"

echo
echo "Installation complete. Check status with:"
echo "  sudo systemctl status rfmp-daemon.service"
echo "  sudo journalctl -u rfmp-daemon.service -f"
