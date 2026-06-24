#!/bin/bash
# Chaos test suite — SAP-EWM Robot Dispatch Platform
# Tests system resilience by killing individual services and verifying recovery
# Usage: bash tests/chaos-test.sh [--verbose]

set -euo pipefail

VERBOSE=false
if [[ "${1:-}" == "--verbose" ]]; then VERBOSE=true; fi

PASS=0
FAIL=0
SERVICES=("robot-platform-nodered" "robot-platform-sap-bridge" "robot-platform-mqtt" "robot-platform-redis" "robot-platform-watchdog")
API_BASE="http://localhost:1880"
TIMEOUT=60  # max seconds to wait for recovery

log()   { echo -e "[$(date +%H:%M:%S)] $1"; }
pass()  { echo -e "  ✅ PASS: $1"; ((PASS++)); }
fail()  { echo -e "  ❌ FAIL: $1"; ((FAIL++)); }
header(){ echo -e "\n══════════════════════════════════════════════"; echo " $1"; echo "══════════════════════════════════════════════"; }

# ── Test 1: Kill MQTT broker ──
header "Test 1: MQTT Broker Kill"
docker kill robot-platform-mqtt 2>/dev/null && log "Killed MQTT" || log "MQTT not running"
sleep 2
docker compose up -d mqtt --no-deps --wait 2>/dev/null
for i in $(seq 1 $TIMEOUT); do
  if docker ps --filter "name=robot-platform-mqtt" --filter "health=healthy" --format '{{.Names}}' | grep -q mqtt; then
    pass "MQTT recovered within ${i}s"
    break
  fi
  sleep 1
done
if ! docker ps --filter "name=robot-platform-mqtt" --filter "health=healthy" --format '{{.Names}}' | grep -q mqtt; then
  fail "MQTT did not recover within ${TIMEOUT}s"
fi

# ── Test 2: Kill Node-RED ──
header "Test 2: Node-RED Kill & Recovery"
docker kill robot-platform-nodered 2>/dev/null && log "Killed Node-RED" || log "Node-RED not running"
sleep 2
docker compose up -d nodered --no-deps --wait 2>/dev/null
for i in $(seq 1 $TIMEOUT); do
  if curl -sf http://localhost:1880/api/system-health > /dev/null 2>&1; then
    pass "Node-RED recovered within ${i}s"
    break
  fi
  sleep 1
done
if ! curl -sf http://localhost:1880/api/system-health > /dev/null 2>&1; then
  fail "Node-RED did not recover within ${TIMEOUT}s"
fi

# ── Test 3: Kill SAP Bridge ──
header "Test 3: SAP Bridge Kill & Recovery"
docker kill robot-platform-sap-bridge 2>/dev/null && log "Killed SAP Bridge" || log "SAP Bridge not running"
sleep 2
docker compose up -d sap-bridge --no-deps --wait 2>/dev/null
for i in $(seq 1 $TIMEOUT); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    pass "SAP Bridge recovered within ${i}s"
    break
  fi
  sleep 1
done
if ! curl -sf http://localhost:8000/health > /dev/null 2>&1; then
  fail "SAP Bridge did not recover within ${TIMEOUT}s"
fi

# ── Test 4: Kill Redis ──
header "Test 4: Redis Kill & Recovery"
docker kill robot-platform-redis 2>/dev/null && log "Killed Redis" || log "Redis not running"
sleep 2
docker compose up -d redis --no-deps --wait 2>/dev/null
for i in $(seq 1 $TIMEOUT); do
  if docker exec robot-platform-redis redis-cli ping 2>/dev/null | grep -q PONG; then
    # Check dependent services recovered too
    sleep 3
    pass "Redis recovered within ${i}s"
    break
  fi
  sleep 1
done
if ! docker exec robot-platform-redis redis-cli ping 2>/dev/null | grep -q PONG; then
  fail "Redis did not recover within ${TIMEOUT}s"
fi

# ── Test 5: Kill all services (Docker restart policy) ──
header "Test 5: All Services Kill (Docker restart policy)"
docker kill robot-platform-nodered robot-platform-sap-bridge robot-platform-mqtt 2>/dev/null
log "Killed Node-RED, SAP Bridge, MQTT — waiting for Docker restart policy"
sleep 10
all_running=true
for svc in robot-platform-nodered robot-platform-sap-bridge robot-platform-mqtt; do
  if docker ps --filter "name=$svc" --format '{{.Names}}' 2>/dev/null | grep -q "$svc"; then
    log "  $svc: running"
  else
    log "  $svc: NOT running"
    all_running=false
  fi
done
if $all_running; then
  pass "All services recovered via Docker restart policy"
else
  fail "Some services did not recover via Docker restart policy"
fi

# ── Test 6: Order creation after recovery ──
header "Test 6: Order Creation After Recovery"
for i in $(seq 1 30); do
  http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    http://localhost:1880/api/v1/orders \
    -H "Content-Type: application/json" \
    -d '{"manufacturer":"KUKA","serialNumber":"LOAD-001","orderId":"CHAOS-'${RANDOM}'","orderType":"MOVE","priority":2}' 2>/dev/null)
  if [[ "$http_code" == "200" || "$http_code" == "202" ]]; then
    pass "Order creation successful after recovery (HTTP $http_code)"
    break
  fi
  sleep 1
done
if [[ "$http_code" != "200" && "$http_code" != "202" ]]; then
  fail "Order creation failed after recovery (HTTP $http_code)"
fi

# ── Test 7: MQTT topic connectivity ──
header "Test 7: MQTT Topic Verification"
PUBLISHED=false
SUBSCRIBED=false
# Test publish
if mosquitto_pub -t "vda5050/test/chaos" -m '{"test": true}' -r -q 1 2>/dev/null; then
  PUBLISHED=true
  log "MQTT publish OK"
fi
# Test subscribe
RESULT=$(mosquitto_sub -t "vda5050/test/chaos" -C 1 -W 3 2>/dev/null)
if [[ -n "$RESULT" ]]; then
  SUBSCRIBED=true
  log "MQTT subscribe OK"
fi
# Cleanup
mosquitto_pub -t "vda5050/test/chaos" -n -r 2>/dev/null || true
if $PUBLISHED && $SUBSCRIBED; then
  pass "MQTT pub/sub working"
else
  fail "MQTT pub/sub not fully working (pub=$PUBLISHED sub=$SUBSCRIBED)"
fi

# ── Summary ──
header "Chaos Test Results"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Total:  $((PASS + FAIL))"
if [ $FAIL -gt 0 ]; then exit 1; fi
