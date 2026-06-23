---
name: degradation-drill-sop
description: Degradation drill SOP — 3/7/14 day drills (network outage, database failure, full stack crash) with pass criteria
---

# 降级演练 SOP

## 3/7/14 天演练计划

### 第 3 天：断网演练
- 模拟：`iptables -A INPUT -j DROP`
- 强制使用纸质单补录
- 通过标准：补录准确率 100%，30 分钟内恢复

### 第 7 天：数据库故障演练
- 模拟：`docker stop robot-platform-redis`
- 验证 10s 内安全模式触发
- 验证纸面单补录流程

### 第 14 天：全栈崩溃演练
- 模拟：`docker-compose down`
- 从 OSS 备份恢复
- 通过标准：30 分钟内全栈恢复
