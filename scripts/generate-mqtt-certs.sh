#!/bin/bash
# Generate MQTT TLS certificates for production
# Usage: bash scripts/generate-mqtt-certs.sh [CERT_DIR]
# Requires: openssl

set -euo pipefail

CERT_DIR="${1:-./mqtt/certs}"
DAYS=3650  # 10 years (CA only — server certs rotate sooner)
SERVER_DAYS=365  # 1 year server cert
CA_KEY="${CERT_DIR}/ca.key"
CA_CERT="${CERT_DIR}/ca.crt"
SERVER_KEY="${CERT_DIR}/server.key"
SERVER_CERT="${CERT_DIR}/server.crt"
SERVER_CSR="${CERT_DIR}/server.csr"

mkdir -p "$CERT_DIR"

echo "=== Generating CA ==="
openssl genrsa -out "$CA_KEY" 4096
openssl req -x509 -new -nodes -key "$CA_KEY" -sha256 -days "$DAYS" \
  -out "$CA_CERT" \
  -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Robot Platform/CN=MQTT CA"

echo "=== Generating Server Key ==="
openssl genrsa -out "$SERVER_KEY" 2048

echo "=== Generating Server CSR ==="
openssl req -new -key "$SERVER_KEY" -out "$SERVER_CSR" \
  -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Robot Platform/CN=mqtt.robot-platform.local"

echo "=== Signing Server Certificate ==="
openssl x509 -req -in "$SERVER_CSR" -CA "$CA_CERT" -CAkey "$CA_KEY" \
  -CAcreateserial -out "$SERVER_CERT" -days "$SERVER_DAYS" -sha256 \
  -extensions v3_req \
  -extfile <(cat <<EOF
[v3_req]
keyUsage = keyEncipherment, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
[alt_names]
DNS.1 = mqtt.robot-platform.local
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF
)

echo "=== Setting Permissions ==="
chmod 600 "$CA_KEY" "$SERVER_KEY"

echo "=== Cleaning Up ==="
rm -f "$SERVER_CSR" "$CA_KEY".srl 2>/dev/null || true

echo "=== Generated Files ==="
ls -la "$CERT_DIR/"
echo ""
echo "Next steps:"
echo "  1. Replace mosquitto.conf with mosquitto-tls.conf"
echo "  2. Add to docker-compose.yml:"
echo "     volumes:"
echo "       - ./mqtt/certs:/mosquitto/certs:ro"
echo "  3. docker compose restart mqtt"
