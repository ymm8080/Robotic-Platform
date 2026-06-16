#!/bin/bash
# SAP-EWM 机器人调度平台每日备份脚本 v3.4
# crontab: 0 2 * * * /opt/robot-platform/scripts/backup.sh

set -euo pipefail

BACKUP_DIR="/backup/robot-platform"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p ${BACKUP_DIR}

echo "[$(date)] 开始备份..."

# 1. 备份 SQLite 数据库
docker exec robot-platform-nodered sqlite3 /data/robot_platform.db ".backup /tmp/robot_platform_backup.db"
docker cp robot-platform-nodered:/tmp/robot_platform_backup.db ${BACKUP_DIR}/robot_platform_${DATE}.db

# 2. 备份 Redis RDB
docker exec robot-platform-redis redis-cli BGSAVE
sleep 5
docker cp robot-platform-redis:/data/dump.rdb ${BACKUP_DIR}/redis_${DATE}.rdb

# 3. 备份 Node-RED 配置
tar czf ${BACKUP_DIR}/nodered_config_${DATE}.tar.gz -C /var/lib/docker/volumes/robot-platform_nodered-data/_data . 2>/dev/null || true

# 4. 备份环境变量和 Secrets
cd /opt/robot-platform
tar czf ${BACKUP_DIR}/secrets_${DATE}.tar.gz .env secrets/ 2>/dev/null || true

# 5. 计算校验和
cd ${BACKUP_DIR}
sha256sum robot_platform_${DATE}.db > robot_platform_${DATE}.db.sha256
sha256sum redis_${DATE}.rdb > redis_${DATE}.rdb.sha256

# 6. 上传至 OSS（如配置）
if command -v aliyun &> /dev/null; then
    aliyun oss cp robot_platform_${DATE}.db oss://your-backup-bucket/robot-platform/db/ 2>/dev/null || true
    aliyun oss cp redis_${DATE}.rdb oss://your-backup-bucket/robot-platform/redis/ 2>/dev/null || true
fi

# 7. 清理旧备份
find ${BACKUP_DIR} -name "*.db" -mtime +7 -delete
find ${BACKUP_DIR} -name "*.rdb" -mtime +7 -delete
find ${BACKUP_DIR} -name "*.tar.gz" -mtime +7 -delete
find ${BACKUP_DIR} -name "*.sha256" -mtime +7 -delete

echo "[$(date)] 备份完成: ${DATE}"
