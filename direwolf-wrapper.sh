#!/bin/bash
set -e

PROFILE="$1"
CONF="$2"

LOCK="/run/direwolf.lock"

# Enforce single instance
exec 9>"$LOCK"
flock -n 9 || exit 0

# Start Direwolf in background
/usr/bin/direwolf -t 0 -p -c "$CONF" &
DW_PID=$!

# Give Direwolf a moment to create KISS socket
for i in {1..10}; do
  [ -S /tmp/kisstnc ] && break
  sleep 0.5
done


# ----- KISS SETUP -----
case "$PROFILE" in
  qmx)
    kissattach /tmp/kisstnc hf
    kissparms -c 1 -p hf
    ;;
  digirig|digilite)
    kissattach /tmp/kisstnc vhf
    kissparms -c 1 -p vhf
    ;;
esac

# Wait on Direwolf
wait $DW_PID

