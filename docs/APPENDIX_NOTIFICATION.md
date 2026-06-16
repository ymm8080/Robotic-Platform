
# =============================================================================
# 附录 E：告警通道降级与容灾（通知不静默）
# =============================================================================
# 风险：飞书/企微全局宕机时，所有 P0 告警静默，运维变成瞎子
# 2023 年飞书曾全局宕机 2 小时，此方案确保该场景下仍有告警出口

## E.1 通道优先级架构

```
P0 致命告警 → 飞书 Webhook（主通道）
           → 企微 Webhook（备用通道，5 秒内无响应切换）
           → 阿里云短信（终极通道，仅 P0，成本约 0.05 元/条）
           → 本地声光报警器（物理兜底，机房内）
```

## E.2 阿里云短信网关配置（终极通道）

```bash
# 1. 阿里云控制台开通短信服务，获取 AccessKey
# 2. 在 .env 中配置
ALIBABA_CLOUD_ACCESS_KEY_ID=your-access-key
ALIBABA_CLOUD_ACCESS_KEY_SECRET=your-secret
ALIBABA_SMS_SIGN_NAME=你的签名
ALIBABA_SMS_TEMPLATE_CODE=SMS_12345678  # 模板内容：【仓储调度】系统熔断：{reason}，请立即处理。

# 3. 在 Watchdog 环境变量中追加
- ALIBABA_CLOUD_ACCESS_KEY_ID=${ALIBABA_CLOUD_ACCESS_KEY_ID}
- ALIBABA_CLOUD_ACCESS_KEY_SECRET=${ALIBABA_CLOUD_ACCESS_KEY_SECRET}
- ALIBABA_SMS_SIGN_NAME=${ALIBABA_SMS_SIGN_NAME}
- ALIBABA_SMS_TEMPLATE_CODE=${ALIBABA_SMS_TEMPLATE_CODE}
- ALIBABA_SMS_PHONE=${RESCUE_OPS_PHONE}  # 接收短信的手机号
```

## E.3 本地声光报警器（物理兜底）

**硬件选型**：USB 蜂鸣器 + 红色警示灯（淘宝约 50 元）

**接线**：插入仓库主管电脑 USB 口

**触发逻辑**（Watchdog HTTP API 扩展）：
```bash
# Watchdog 检测到飞书/企微连续 3 次发送失败时
curl -X POST http://localhost:9090/alarm/trigger   -d '{"type": "PHYSICAL_ALARM", "reason": "所有网络告警通道失效"}'

# 主管电脑上的守护进程收到后
# 1. USB 蜂鸣器持续鸣响
# 2. 红色警示灯闪烁
# 3. 弹窗显示："系统熔断，所有网络告警通道失效，请立即检查服务器！"
```

**关闭方式**：
```bash
curl -X POST http://localhost:9090/alarm/reset
# 或物理按下蜂鸣器上的按钮
```

## E.4 通道降级演练（每月执行）

```bash
# 模拟飞书宕机：阻断飞书 Webhook IP
sudo iptables -A OUTPUT -p tcp --dst 123.56.0.0/16 -j DROP  # 飞书 IP 段

# 观察 5 分钟内：
# 1. 企微是否收到告警（备用通道切换）
# 2. 如果企微也阻断，短信是否发出
# 3. 如果短信也失败，物理报警器是否触发

# 恢复
sudo iptables -F
```

## E.5 成本与安全控制

| 通道 | 成本 | 日限 | 触发条件 |
|------|------|------|---------|
| 飞书 Webhook | 免费 | 无限制 | 所有级别 |
| 企微 Webhook | 免费 | 无限制 | 飞书失败时 |
| 阿里云短信 | ~0.05 元/条 | 100 条/天 | P0 且飞书+企微失败 |
| 物理报警器 | 一次性 50 元 | 无限制 | 所有网络通道失败 |

**防止短信轰炸**：
- Watchdog 内置短信冷却：同一原因 30 分钟内最多发送 1 条
- 日限 100 条，超限后仅记录日志，不发送
