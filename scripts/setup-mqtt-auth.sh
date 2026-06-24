#!/bin/bash
# MQTT Authentication Setup — enable password + ACL for production
# Usage: bash scripts/setup-mqtt-auth.sh [password]
# Requires: mosquitto_passwd (part of mosquitto-clients)

set -euo pipefail

MQTT_DIR="./mqtt"
PASSWD_FILE="${MQTT_DIR}/passwd"
ACL_FILE="${MQTT_DIR}/acl"
PASSWORD="${1:-$(openssl rand -base64 16)}"

echo "=== MQTT Auth Setup ==="

# 1. Create password file
mkdir -p "$MQTT_DIR"
touch "$PASSWD_FILE" "$ACL_FILE"

# 2. Add robot-platform user
mosquitto_passwd -b "$PASSWD_FILE" robot-platform "$PASSWORD"
echo "User 'robot-platform' created"

# 3. Create ACL file
cat > "$ACL_FILE" << 'ACLEOF'
# MQTT ACL — VDA5050 Topic Authorization
user robot-platform
topic read vda5050/+/+/+
topic write vda5050/+/+/+

user monitor
topic read vda5050/+/+/state
topic read vda5050/+/+/connection

user admin
topic read #
topic write #

topic read $SYS/broker/#
ACLEOF
echo "ACL file created"

# 4. Update mosquitto.conf to enable auth
if grep -q "^allow_anonymous true" "${MQTT_DIR}/mosquitto.conf"; then
  sed -i 's/^allow_anonymous true/allow_anonymous false/' "${MQTT_DIR}/mosquitto.conf"
  sed -i 's|^#password_file /mosquitto/config/passwd|password_file /mosquitto/config/passwd|' "${MQTT_DIR}/mosquitto.conf"
  sed -i 's|^#acl_file /mosquitto/config/acl|acl_file /mosquitto/config/acl|' "${MQTT_DIR}/mosquitto.conf"
  echo "mosquitto.conf updated (auth enabled)"
else
  echo "mosquitto.conf already has auth configured"
fi

echo ""
echo "=== MQTT Auth Setup Complete ==="
echo "Password: $PASSWORD"
echo ""
echo "Next steps:"
echo "  1. docker compose restart mqtt"
echo "  2. Test: mosquitto_pub -t 'healthcheck' -m 'test' -u robot-platform -P '$PASSWORD'"
echo "  3. Save password in password manager"
