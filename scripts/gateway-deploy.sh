#!/bin/bash
# =============================================================================
# SAP-EWM 消息网关部署脚本 (v3.5)
# 用途：构建并启动消息网关服务
# 使用：bash scripts/gateway-deploy.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "  SAP-EWM Message Gateway Deploy (v3.5)"
echo "=========================================="

# 1. 检查 .env 文件
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "[ERROR] .env file not found. Copy .env.example to .env and configure."
    exit 1
fi

# 2. 检查 SMTP 密码文件
SMTP_SECRET="$PROJECT_ROOT/secrets/smtp_password.txt"
if [ ! -f "$SMTP_SECRET" ]; then
    echo "[WARN] SMTP password file not found at $SMTP_SECRET"
    echo "       Create it if email notifications are needed:"
    echo "       echo 'your_smtp_password' > $SMTP_SECRET"
    # Create empty file to prevent Docker Compose error
    echo "" > "$SMTP_SECRET"
fi

# 3. 备份当前配置（变更前备份铁律）
BACKUP_DIR="$PROJECT_ROOT/ops/backup/gateway_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp "$PROJECT_ROOT/docker-compose.yml" "$BACKUP_DIR/"
cp "$PROJECT_ROOT/.env" "$BACKUP_DIR/"
echo "[OK] Backup saved to $BACKUP_DIR"

# 4. 构建消息网关镜像
echo "[BUILD] Building message-gateway image..."
docker compose build message-gateway

# 5. 启动基础设施服务（Kafka + Elasticsearch）
echo "[START] Starting infrastructure services (Kafka, Elasticsearch)..."
docker compose up -d kafka elasticsearch

# 6. 等待基础设施就绪
echo "[WAIT] Waiting for Kafka to be healthy..."
for i in $(seq 1 30); do
    if docker inspect --format='{{.State.Health.Status}}' robot-platform-kafka 2>/dev/null | grep -q healthy; then
        echo "[OK] Kafka is healthy"
        break
    fi
    sleep 2
    if [ $i -eq 30 ]; then
        echo "[ERROR] Kafka failed to become healthy in 60s"
        exit 1
    fi
done

echo "[WAIT] Waiting for Elasticsearch to be healthy..."
for i in $(seq 1 30); do
    if docker inspect --format='{{.State.Health.Status}}' robot-platform-elasticsearch 2>/dev/null | grep -q healthy; then
        echo "[OK] Elasticsearch is healthy"
        break
    fi
    sleep 2
    if [ $i -eq 30 ]; then
        echo "[ERROR] Elasticsearch failed to become healthy in 60s"
        exit 1
    fi
done

# 7. 启动消息网关
echo "[START] Starting message-gateway..."
docker compose up -d message-gateway

# 8. 验证健康状态
echo "[VERIFY] Checking gateway health..."
sleep 5
for i in $(seq 1 10); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/health 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "[OK] Message Gateway is healthy (HTTP 200)"
        echo ""
        echo "=========================================="
        echo "  Deployment Complete!"
        echo "=========================================="
        echo "  Gateway URL:  http://localhost:8010"
        echo "  Health:       http://localhost:8010/health"
        echo "  Audit Logs:   http://localhost:8010/api/v1/audit/logs"
        echo "  Backup:       $BACKUP_DIR"
        echo "=========================================="
        exit 0
    fi
    sleep 2
done

echo "[ERROR] Message Gateway failed to start properly"
echo "        Check logs: docker logs robot-platform-message-gateway"
exit 1
