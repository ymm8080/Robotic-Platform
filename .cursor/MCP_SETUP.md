# ⚠️ 警告：MCP 工具默认禁用！

仅当你本地已安装 `uv` (Python) 和 `Node.js` 时，才可将 `mcp.json.disabled` 重命名为 `mcp.json` 启用。
如果你不知道这是什么，请保持禁用，使用 VS Code 插件替代。

降级方案：
- SQLite：用 VS Code 的 SQLite Viewer 插件查看数据库
- Redis：用命令行 `docker exec -it robot-platform-redis redis-cli` 查看缓存
- Docker：用命令行 `docker logs` 查看容器日志
- MQTT：用 MQTTX 客户端订阅和发布消息
