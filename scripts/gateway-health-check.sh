#!/bin/bash
# =============================================================================
# SAP-EWM 消息网关健康检查脚本 (v3.5)
# 用途：检查消息网关及其依赖服务的健康状态
# 使用：bash scripts/gateway-health-check.sh
# 可用于 crontab 定期检查
# =============================================================================

set -euo pipefail

GATEWAY_URL="http://localhost:8010"
HEALTH_ENDPOINT="/health"
LOG_FILE="/var/log/gateway-health.log"
ALERT_WEBHOOK="${FEISHU_WEBHOOK_URL:-}"

# 辅助函数
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
    echo "$1"
}

send_alert() {
    if [ -n "$ALERT_WEBHOOK" ]; then
        curl -s -X POST "$ALERT_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"msg_type\":\"text\",\"content\":{\"text\":\"🚨 消息网关健康检查失败: $1\"}}" \
            > /dev/null 2>&1 || true
    fi
}

ALL_OK=true

# 1. 检查消息网关
GATEWAY_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$GATEWAY_URL$HEALTH_ENDPOINT" 2>/dev/null || echo "000")
if [ "$GATEWAY_HTTP" = "200" ]; then
    log "[OK] Message Gateway: healthy"
else
    log "[FAIL] Message Gateway: HTTP $GATEWAY_HTTP"
    ALL_OK=false
fi

# 2. 检查 Kafka
KAFKA_HEALTHY=$(docker inspect --format='{{.State.Health.Status}}' robot-platform-kafka 2>/dev/null || echo "not_found")
if [ "$KAFKA_HEALTHY" = "healthy" ]; then
    log "[OK] Kafka: healthy"
else
    log "[FAIL] Kafka: $KAFKA_HEALTHY"
    ALL_OK=false
fi

# 3. 检查 Elasticsearch
ES_HEALTHY=$(docker inspect --format='{{.State.Health.Status}}' robot-platform-elasticsearch 2>/dev/null || echo "not_found")
if [ "$ES_HEALTHY" = "healthy" ]; then
    log "[OK] Elasticsearch: healthy"
else
    log "[FAIL] Elasticsearch: $ES_HEALTHY"
    ALL_OK=false
fi

# 4. 检查 Redis (gateway uses DB 2)
REDIS_PING=$(docker exec robot-platform-redis redis-cli -a "${REDIS_PASSWORD:-robot-platform-redis}" ping 2>/dev/null || echo "FAIL")
if echo "$REDIS_PING" | grep -q PONG; then
    log "[OK] Redis: healthy"
else
    log "[FAIL] Redis: $REDIS_PING"
    ALL_OK=false
fi

# 5. 汇总
if [ "$ALL_OK" = true ]; then
    log "[SUMMARY] All gateway components healthy"
    exit 0
else
    log "[SUMMARY] One or more components unhealthy!"
    send_alert "一个或多个消息网关组件不健康，请检查日志: $LOG_FILE"
    exit 1
fi
