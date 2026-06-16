#!/bin/bash
# 清理旧日志脚本（限流时运维手动执行）

set -euo pipefail

echo "清理容器日志..."

# 清理 Docker 容器日志（json-file 驱动）
for container in robot-platform-nodered robot-platform-sap-bridge robot-platform-watchdog; do
    if docker inspect $container &>/dev/null; then
        log_path=$(docker inspect --format='{{.LogPath}}' $container 2>/dev/null)
        if [ -n "$log_path" ] && [ -f "$log_path" ]; then
            echo "  清空 $container 日志"
            sudo sh -c "> $log_path"
        fi
    fi
done

# 清理应用日志
find /var/log -name "*.log" -mtime +7 -delete 2>/dev/null || true
find /app/logs -name "*.log" -mtime +7 -delete 2>/dev/null || true

echo "清理完成"
