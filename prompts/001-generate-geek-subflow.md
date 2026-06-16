# Prompt: 生成极智嘉机器人 Sub-flow

## 输入
- 机器人型号：GEEK+ M100 / P800 / RS8
- 任务类型：搬运 / 拣选 / 盘点
- 目标库位：A01-02-03

## 输出
- Node-RED Sub-flow JSON（仅 Function 节点 JS 代码）
- 必须包含：急停检查、电量检查、区域锁检查
- 禁止输出完整的 flows.json

## 限制
- 仅使用 JavaScript (ES6+)
- 必须调用 safeLoop/safeExec
- 必须处理 api_deviation_log 记录
