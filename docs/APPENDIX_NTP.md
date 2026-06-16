
# =============================================================================
# 附录 D：NTP 时钟同步配置（物理级防呆）
# =============================================================================
# 风险：宿主机时钟漂移会导致 Redis TTL 错乱、审计日志时序颠倒、等保审计失败
# 必须配置项，不可跳过

## D.1 宿主机 NTP 配置（Ubuntu/Debian）

```bash
# 安装 chrony（比 ntpd 更精准，支持虚拟机时钟补偿）
sudo apt-get update && sudo apt-get install -y chrony

# 配置阿里云 NTP 源（国内）
sudo tee /etc/chrony/chrony.conf << 'EOF'
pool ntp.aliyun.com iburst
pool ntp1.aliyun.com iburst
pool time1.cloud.tencent.com iburst

# 允许本地 Docker 网络同步（可选）
allow 172.20.0.0/16

# 记录时钟漂移日志（等保审计用）
log tracking measurements statistics
logdir /var/log/chrony
EOF

# 启动并启用开机自启
sudo systemctl enable chrony
sudo systemctl restart chrony

# 验证同步状态
chronyc tracking
# 预期：Leap status: Normal，Reference ID 为有效 NTP 服务器

# 验证时间偏差
chronyc sources -v
# 预期：所有源状态为 ^*（已同步）或 ^+（候选），LastRx 列显示最近接收时间
```

## D.2 容器时钟挂载（已在 docker-compose.yml 中配置）

每个业务服务已挂载：
```yaml
volumes:
  - /etc/localtime:/etc/localtime:ro
```

这确保容器内 `date` 命令与宿主机物理时钟一致，不受容器内 NTP 守护进程影响。

## D.3 时钟漂移监控（Watchdog 自动检测）

Watchdog 已内置时钟漂移检测逻辑：
- 每 60 秒对比容器内时间与 Redis 服务器时间
- 偏差 > 5 秒时触发 `"CLOCK_DRIFT"` 告警
- 偏差 > 30 秒时自动进入安全模式（防止时序错乱导致状态机异常）

## D.4 等保三级时钟要求

1. **审计日志时戳**：所有 `audit_log` 表记录必须使用 UTC 时间戳（已配置）
2. **时钟同步证明**：等保测评时需出示 `chronyc tracking` 输出截图
3. **漂移容差**：生产环境要求时钟偏差 < 1 秒（虚拟机建议开启 VMware Tools 时间同步）

## D.5 故障排查

```bash
# 检查宿主机时钟
 timedatectl status
# 预期：System clock synchronized: yes
#       NTP service: active

# 检查容器时钟是否与宿主机一致
docker exec robot-platform-nodered date
date
# 预期：两者输出完全一致（秒级）

# 如果不同步，强制同步
sudo chronyc makestep
```
