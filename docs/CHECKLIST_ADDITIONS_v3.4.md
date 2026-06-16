
# =============================================================================
# 48h-checklist-v3.4.md 新增检查项（3项）
# =============================================================================

### 39. NTP 时钟同步验证 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | 物理级防呆补充 |
| **风险** | 时钟漂移导致 Redis TTL 错乱、审计日志时序颠倒、等保审计失败 |
| **命令/方法** | 1. `chronyc tracking`（宿主机）<br>2. `docker exec robot-platform-nodered date && date`（对比宿主机与容器）<br>3. `docker exec robot-platform-redis redis-cli TTL system:safe_mode`（验证 TTL 逻辑） |
| **通过标准** | 1. chrony 状态 `Leap status: Normal`，偏差 < 1ms<br>2. 容器与宿主机时间完全一致（秒级）<br>3. 写入 `system:safe_mode` TTL=3600，实际过期时间与预期一致（误差 < 5 秒） |
| **佐证** | `chronyc tracking` 截图 + 容器/宿主机时间对比截图 |

### 40. 告警通道降级演练 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | 通知容灾补充 |
| **风险** | 飞书/企微宕机时所有 P0 告警静默，运维失明 |
| **命令/方法** | 1. `sudo iptables -A OUTPUT -p tcp --dst 123.56.0.0/16 -j DROP`（阻断飞书 IP 段）<br>2. 触发 P0 告警（如 `docker exec robot-platform-redis redis-cli DEBUG OOM`）<br>3. 观察 5 分钟内告警通道切换 |
| **通过标准** | 1. 飞书发送失败（日志记录）<br>2. 企微收到告警（备用通道切换 <= 10 秒）<br>3. 如果企微也阻断，短信发出（终极通道 <= 60 秒）<br>4. 如果短信也失败，物理报警器触发（蜂鸣器鸣响 + 红灯闪烁） |
| **佐证** | 各通道告警截图 + 物理报警器照片/视频 |
| **恢复** | `sudo iptables -F` |

### 41. 灾难恢复实战演练 [P0]

| 属性 | 内容 |
|------|------|
| **来源** | 备份验证补充 |
| **风险** | 有备份但从未恢复过，真灾难时无法救命 |
| **命令/方法** | 在**测试环境**执行：<br>1. `sudo rm -rf /var/lib/docker/volumes/robot-platform_*`<br>2. 从 OSS 下载最新备份<br>3. 按 DEPLOY_GUIDE 附录 F 恢复数据<br>4. `docker compose -f docker-compose-v3.4-FINAL.yml up -d` |
| **通过标准** | 1. 恢复耗时 <= 30 分钟<br>2. 最近 1 小时订单数据完整（`SELECT COUNT(*) FROM orders WHERE created_at > datetime('now', '-1 hour')` 与备份前一致）<br>3. 审计日志无断点（时间戳连续）<br>4. 机器人全部 ONLINE<br>5. 主管签字确认 |
| **佐证** | 恢复过程录屏 + 数据完整性校验脚本输出 + 三方签字 |
| **频率** | 每季度一次，留存演练报告 |
