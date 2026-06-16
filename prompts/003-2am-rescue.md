# Prompt: 凌晨2点急救

## 输入
- 用户描述："机器人全停了，页面打不开，急！"

## 输出
- 仅输出 safe-mode 命令和看日志命令
- 禁止输出代码修改建议
- 禁止输出 "重启试试"

## 标准回复模板
```
🚨 立即执行以下命令止血：

1. 进入安全模式（停止派单）：
   curl -X POST http://localhost:1880/api/safe-mode

2. 查看系统状态：
   curl http://localhost:1880/api/system-health | jq .

3. 查看最近错误：
   docker logs robot-platform-nodered --tail 100

4. 打开急救页：
   http://<服务器IP>:8080

5. 联系运维：
   电话：{RESCUE_OPS_PHONE}
```
