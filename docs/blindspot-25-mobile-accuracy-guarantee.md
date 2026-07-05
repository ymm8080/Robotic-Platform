# 盲区二十五：移动端准确率保障

## 问题

当告警通知从 Web UI 扩展到微信、飞书、钉钉等移动端时，操作准确率面临严峻挑战：

1. **自然语言歧义**：用户打字"停掉 R-01"可能被 LLM 误解为停掉 R-10
2. **平台消息格式差异**：微信/飞书/钉钉的卡片交互能力不同，可能导致按钮误触
3. **用户身份不确定**：平台用户ID与系统用户ID未绑定，无法确认操作权限
4. **重复点击**：网络延迟导致用户多次点击同一按钮
5. **操作对象混淆**：用户看到多条告警，在错误的卡片上点击了确认按钮
6. **超时操作**：告警已过期但用户仍点击了执行按钮

## 解决方案：六重准确率保障机制

所有移动端操作必须经过六重校验，任何一层失败直接拒绝，状态机不受影响。

### Layer 1: 身份验证 (Identity)
- 验证平台用户是否已绑定系统用户
- Redis: `gateway:user_binding:{platform}:{platform_user_id}` → `bound_user_id`
- 未绑定用户的所有操作直接拒绝

### Layer 2: 权限校验 (Permission)
- 验证用户是否拥有该操作类型的权限
- Redis: `gateway:permissions:{user_id}` → SET of action_types
- 支持通配符 `*` (管理员权限)
- 只读操作 (dismiss/view) 跳过此层

### Layer 3: 对象校验 (Object)
- 验证目标对象存在且处于可操作状态
- 调用核心平台 API 查询对象当前状态
- 示例：急停 IDLE 状态的机器人 → 拒绝（无需急停）
- 示例：取消已完成订单 → 拒绝（终态不可逆）

### Layer 4: 防重放 (Anti-Replay)
- 计算操作指纹: `SHA256(user_id + action_type + target_id + correlation_id)`
- Redis SETNX + TTL (确认超时 + 60s 缓冲)
- 同一指纹在 TTL 内只能处理一次
- 防止网络重传和用户重复点击

### Layer 5: 二次确认 (Secondary Confirmation)
- 危险操作（急停、取消订单、召回、区域封锁）需要二次确认
- 第一次点击 → 生成 confirm_token → 发送二次确认卡片
- 第二次点击（带 confirm_token）→ 校验 token 有效性 + 操作匹配 → 执行
- Token TTL = 5 分钟，超时自动失效

### Layer 6: 执行前校验 (Pre-Execution)
- 检查系统是否处于安全模式（安全模式下仅允许急停和解锁）
- 检查机器人急停状态（急停状态下不能召回）
- 检查区域锁状态（已锁定区域不能重复锁定）
- 确保操作在当前时刻可以安全执行

## 操作状态机

```
INIT → NOTIFIED → CONFIRMING → CONFIRMED → EXECUTING → SUCCESS
                                      ↓           ↓         ↓
                                  CANCELLED    CANCELLED  FAILED
                                                           TIMEOUT
```

### 状态流转约束
- NOTIFIED → CONFIRMING: 仅允许一次状态转换（防重复点击）
- CONFIRMING → CONFIRMED: 必须在 5 分钟内完成，超时自动 CANCELLED
- EXECUTING → SUCCESS/FAILED/TIMEOUT: 三态互斥，不可回退
- 任意状态 → CANCELLED: 仅在 CONFIRMING 阶段允许

## 关键设计决策

1. **结构化按钮 > 自然语言**：所有写操作必须通过按钮触发，禁止 NLU 直接执行
2. **按钮文案包含操作对象**：如"确认急停 R-01"，而非仅"确认急停"
3. **平台签名必须验证**：未验证的回调直接丢弃，不进入校验流程
4. **审计日志不可篡改**：所有操作（含失败的）写入 ES，保留 ≥3 年
5. **CowAgent 隔离**：AI 查询助手只注册只读工具，与写操作链路物理隔离

## 验收标准

- [ ] 模拟未绑定用户操作 → 被拒绝 (Layer 1)
- [ ] 模拟无权限用户操作 → 被拒绝 (Layer 2)
- [ ] 模拟操作不存在的对象 → 被拒绝 (Layer 3)
- [ ] 模拟重复点击同一按钮 → 仅第一次执行 (Layer 4)
- [ ] 模拟危险操作 → 收到二次确认卡片 (Layer 5)
- [ ] 模拟安全模式下非急停操作 → 被拒绝 (Layer 6)
- [ ] 所有操作（含失败）可在审计日志中查询
- [ ] 准确率 100%（零误操作）
