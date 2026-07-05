// =============================================================================
// Node-RED Function 节点：消息网关事件生产者 (v3.5)
// 用途：将系统告警事件发送到 Kafka，由消息网关消费并分发到各平台
// 部署：在告警触发流程后添加此 Function 节点
// =============================================================================
// 输入 msg 结构：
//   msg.payload = {
//     alert_id: "ALT_20260705_001",
//     priority: "P0",
//     title: "机器人路径冲突告警",
//     content: "机器人 R-01 在 Zone-A 与 R-02 路径冲突",
//     action_type: "robot_stop",
//     target_type: "robot",
//     target_id: "R-01",
//     recipients: ["USER_10086", "USER_10087"],
//     require_confirm: true,
//     correlation_id: "corr_abc789"
//   }
// 输出 msg 结构：
//   msg.topic = "platform_alerts"  (Kafka topic)
//   msg.payload = JSON 格式的告警事件

const KAFKA_TOPIC = "platform_alerts";

// 构造告警事件
const alertEvent = {
  alert_id: msg.payload.alert_id || `ALT_${Date.now()}`,
  priority: msg.payload.priority || "P2",
  title: msg.payload.title || "未命名告警",
  content: msg.payload.content || "",
  action_type: msg.payload.action_type || "dismiss",
  target: {
    target_type: msg.payload.target_type || "robot",
    target_id: msg.payload.target_id || ""
  },
  channels: msg.payload.channels || [],  // 空数组=按优先级自动选择
  recipients: msg.payload.recipients || [],
  require_confirm: msg.payload.require_confirm !== false,
  confirm_type: msg.payload.require_confirm !== false ? "secondary" : "none",
  correlation_id: msg.payload.correlation_id || msg.payload.alert_id || "",
  expire_at: msg.payload.expire_at || new Date(Date.now() + 3600000).toISOString(),
  source: "node-red",
  timestamp: new Date().toISOString()
};

// 发送到 Kafka
msg.topic = KAFKA_TOPIC;
msg.payload = JSON.stringify(alertEvent);

// 日志
node.log(`[GatewayProducer] Alert sent to Kafka: alert_id=${alertEvent.alert_id}, priority=${alertEvent.priority}, action=${alertEvent.action_type}, target=${alertEvent.target.target_id}`);

return msg;
