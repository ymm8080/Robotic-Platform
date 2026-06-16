
# =============================================================================
# 附录 F：灾难恢复与备份验证（真正恢复过才算备份）
# =============================================================================
# 风险：90% 团队有备份脚本，10% 真正恢复过。宿主机硬盘物理损坏时，备份是唯一救命稻草。

## F.1 备份策略（3-2-1 原则）

```
3 份副本：本地 + 异地 + 云存储
2 种介质：磁盘 + 对象存储（OSS/S3）
1 份离线：每月一次离线备份（不可被勒索软件加密）
```

## F.2 自动备份脚本（每日凌晨 2 点执行）

```bash
#!/bin/bash
# /app/scripts/backup.sh
# 建议放入 crontab：0 2 * * * /app/scripts/backup.sh

set -euo pipefail

BACKUP_DIR="/backup/robot-platform"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p ${BACKUP_DIR}

# 1. 备份 SQLite 数据库（在线热备，WAL 模式支持）
docker exec robot-platform-nodered sqlite3 /data/robot_platform.db ".backup /tmp/robot_platform_backup.db"
docker cp robot-platform-nodered:/tmp/robot_platform_backup.db ${BACKUP_DIR}/robot_platform_${DATE}.db

# 2. 备份 Redis RDB
docker exec robot-platform-redis redis-cli BGSAVE
sleep 5  # 等待 BGSAVE 完成
docker cp robot-platform-redis:/data/dump.rdb ${BACKUP_DIR}/redis_${DATE}.rdb

# 3. 备份 Node-RED flows 和配置
tar czf ${BACKUP_DIR}/nodered_config_${DATE}.tar.gz -C /var/lib/docker/volumes/robot-platform_nodered-data/_data .

# 4. 备份环境变量和 Secrets（加密存储）
tar czf ${BACKUP_DIR}/secrets_${DATE}.tar.gz -C /opt/robot-platform .env secrets/

# 5. 上传至 OSS（阿里云）
aliyun oss cp ${BACKUP_DIR}/robot_platform_${DATE}.db oss://your-backup-bucket/robot-platform/db/
aliyun oss cp ${BACKUP_DIR}/redis_${DATE}.rdb oss://your-backup-bucket/robot-platform/redis/
aliyun oss cp ${BACKUP_DIR}/nodered_config_${DATE}.tar.gz oss://your-backup-bucket/robot-platform/config/

# 6. 清理旧备份（本地保留 7 天，OSS 保留 30 天）
find ${BACKUP_DIR} -name "*.db" -mtime +7 -delete
find ${BACKUP_DIR} -name "*.rdb" -mtime +7 -delete
find ${BACKUP_DIR} -name "*.tar.gz" -mtime +7 -delete

echo "[$(date)] 备份完成: ${DATE}"
```

## F.3 灾难恢复演练（每季度强制执行）

**场景**：模拟宿主机硬盘物理损坏

```bash
# 步骤 1：在测试环境执行毁灭性操作（⚠️ 绝不在生产环境执行）
ssh test-server
sudo systemctl stop docker
cd /var/lib/docker/volumes/
sudo rm -rf robot-platform_*

# 步骤 2：从备份恢复
# 2.1 重新创建目录
mkdir -p /opt/robot-platform
cd /opt/robot-platform

# 2.2 下载最新备份
aliyun oss cp oss://your-backup-bucket/robot-platform/db/robot_platform_$(date +%Y%m%d)*.db ./restore/
aliyun oss cp oss://your-backup-bucket/robot-platform/redis/redis_$(date +%Y%m%d)*.rdb ./restore/
aliyun oss cp oss://your-backup-bucket/robot-platform/config/nodered_config_$(date +%Y%m%d)*.tar.gz ./restore/

# 2.3 恢复数据
docker volume create robot-platform_nodered-data
docker volume create robot-platform_redis-data

# 恢复 SQLite
docker run --rm -v robot-platform_nodered-data:/data -v $(pwd)/restore:/restore nodered/node-red:3.1.9   cp /restore/robot_platform_*.db /data/robot_platform.db

# 恢复 Redis
docker run --rm -v robot-platform_redis-data:/data -v $(pwd)/restore:/restore redis:7-alpine   cp /restore/redis_*.rdb /data/dump.rdb

# 2.4 重新部署
docker compose -f docker-compose-v3.4-FINAL.yml up -d

# 步骤 3：验证
# 3.1 系统健康
curl http://localhost:1880/api/system-health | jq .
# 3.2 最近 1 小时数据完整性
sqlite3 /var/lib/docker/volumes/robot-platform_nodered-data/_data/robot_platform.db   "SELECT COUNT(*) FROM orders WHERE created_at > datetime('now', '-1 hour');"
# 3.3 审计日志连续性
sqlite3 /var/lib/docker/volumes/robot-platform_nodered-data/_data/robot_platform.db   "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 5;"

# 通过标准：
# - 系统启动时间 <= 30 分钟
# - 最近 1 小时订单数据完整（无丢失）
# - 审计日志无断点（时间戳连续）
# - 机器人状态正常（全部 ONLINE）
```

## F.4 备份完整性校验（每日自动）

```bash
# 在备份脚本末尾追加校验
# 计算校验和
sha256sum ${BACKUP_DIR}/robot_platform_${DATE}.db > ${BACKUP_DIR}/robot_platform_${DATE}.db.sha256

# 上传校验和
aliyun oss cp ${BACKUP_DIR}/robot_platform_${DATE}.db.sha256 oss://your-backup-bucket/robot-platform/checksum/

# 次日自动验证
# 下载备份和校验和，重新计算比对
```

## F.5 等保三级备份要求

1. **备份频率**：关键数据每日全量备份，日志数据实时同步
2. **留存期限**：备份数据保留 >= 6 个月（与审计日志对齐）
3. **恢复演练**：每季度至少一次完整恢复演练，留存演练报告
4. **离线备份**：每月一次物理离线备份（刻录光盘或移动硬盘），存放异地
