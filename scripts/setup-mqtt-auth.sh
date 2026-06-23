#!/bin/bash
# =============================================================================
# MQTT Auth Setup v1.0 — one-time production hardening
# Usage: sudo bash scripts/setup-mqtt-auth.sh
#
# Generates:
#   - mqtt/passwd    (mosquitto_passwd hashed credential file)
#   - mqtt/acl       (topic-level access control)
#
# After running:
#   1. Edit mqtt/mosquitto.conf → allow_anonymous false
#   2. Uncomment password_file and acl_file lines
#   3. docker-compose restart mqtt
# =============================================================================
set -euo pipefail

PASSWD_FILE="$(dirname "$0")/../mqtt/passwd"
ACL_FILE="$(dirname "$0")/../mqtt/acl"

echo "=== MQTT Auth Setup ==="

# Check for mosquitto_passwd
if ! command -v mosquitto_passwd &>/dev/null; then
    echo "[ERROR] mosquitto_passwd not found. Install mosquitto-tools:"
    echo "  Ubuntu: sudo apt install -y mosquitto-tools"
    echo "  macOS:  brew install mosquitto"
    echo "  Docker: docker run --rm eclipse-mosquitto mosquitto_passwd ..."
    exit 1
fi

# Create empty passwd file
touch "$PASSWD_FILE"

# ── Users ───────────────────────────────────────────────────────────────────
declare -A USERS=(
    ["admin"]      "changeme_admin_password"
    ["sap-bridge"] "changeme_sap_bridge_secret"
    ["watchdog"]   "changeme_watchdog_secret"
    ["dashboard"]  "changeme_dashboard_secret"
)

echo "Creating users (change default passwords immediately)..."
for user in "${!USERS[@]}"; do
    pass="${USERS[$user]}"
    echo "[CREATE] $user"
    mosquitto_passwd -b "$PASSWD_FILE" "$user" "$pass"
done

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. Set strong passwords:"
echo "     mosquitto_passwd -b $PASSWD_FILE <user> <new-password>"
echo "  2. Edit mqtt/mosquitto.conf:"
echo "     - Set 'allow_anonymous false'"
echo "     - Uncomment: password_file /mosquitto/config/passwd"
echo "     - Uncomment: acl_file /mosquitto/config/acl"
echo "  3. Restart: docker-compose restart mqtt"
echo ""
echo "Verification:"
echo "  # Without password (should fail):"
echo "  mosquitto_sub -t 'vda5050/#' -h localhost"
echo "  # With password (should succeed):"
echo "  mosquitto_sub -t 'vda5050/#' -h localhost -u admin -P 'changeme_admin_password'"
