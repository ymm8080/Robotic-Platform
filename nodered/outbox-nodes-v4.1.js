// =============================================================================
// Node-RED Outbox Function Nodes v4.1
// 替换：require('sqlite3') 直连 SQLite → HTTP 调用 sap-bridge API → PostgreSQL
//
// 按 Iron Rule #7：只输出 Function 节点 JS 代码，由用户粘贴到 flows.json
// 共 4 个节点需要替换：
//   1. outbox_query      — 查询 pending outbox 事件
//   2. outbox_update     — 根据 HTTP 响应更新状态
//   3. outbox_deadletter — 写入死信队列
//   4. outbox_http_fail  — HTTP 请求失败兜底
// =============================================================================


// =============================================================================
// 节点 1: outbox_query
// 替换原 require('sqlite3') 直查 → HTTP GET sap-bridge
// =============================================================================
/*
// 前置：需要一个 HTTP Request 节点 (method=GET) 指向:
//   http://sap-bridge:8000/api/v1/outbox/pending?limit=20
// 然后将响应传入此 Function 节点处理

// 如果仍用 Function 节点发 HTTP 请求（不依赖 HTTP Request 节点）:
*/
const sapBridgeUrl = context.env.get('SAP_BRIDGE_URL') || 'http://sap-bridge:8000';
const limit = 20;

// 使用 Node.js 内置 http 模块（同步阻塞不适用于 Function 节点）
// 推荐方案：配合 HTTP Request 节点使用，此节点仅处理响应

// 方案A：如果上游是 HTTP Request 节点 (GET /api/v1/outbox/pending)
const data = msg.payload || {};
const events = data.events || [];

if (events.length === 0) {
    msg.payload = [];
    msg._count = 0;
    return msg;
}

msg.payload = events;
msg._count = events.length;
msg._index = 0;
node.status({fill:'blue', shape:'dot', text: events.length + ' pending'});
return msg;

/*
// 方案B：如果需要在 Function 节点内直接发 HTTP 请求（使用 http请求节点更佳）
// 请在 flows.json 中添加一个 HTTP Request 节点:
//   method: GET
//   url: http://sap-bridge:8000/api/v1/outbox/pending?limit=20
//   return: parsed JSON
// 然后将此 Function 节点接在 HTTP Request 节点之后
*/


// =============================================================================
// 节点 2: outbox_update
// 替换原 require('sqlite3') 直更新 → HTTP POST sap-bridge
// =============================================================================
/*
// 前置：需要一个 HTTP Request 节点 (method=POST) 指向:
//   http://sap-bridge:8000/api/v1/outbox/{event_id}/update
//   body: { "status": "SENT" | "FAILED", "last_error": "..." }
//
// 此节点构建请求体，HTTP Request 节点发送请求，后续节点处理响应
*/

const outboxId = msg._outbox_id;
const orderId = msg._order_id;
const statusCode = msg.statusCode || 500;

// 构建请求体
if (statusCode >= 200 && statusCode < 300) {
    // 成功
    msg.method = 'POST';
    msg.url = (context.env.get('SAP_BRIDGE_URL') || 'http://sap-bridge:8000') + '/api/v1/outbox/' + outboxId + '/update';
    msg.payload = { status: 'SENT' };
    msg._success = true;
    node.status({fill:'green', shape:'dot', text:'sent #' + outboxId});
    node.warn('[OUTBOX] Sent event #' + outboxId + ' (order=' + orderId + ')');
} else {
    // 失败
    msg.method = 'POST';
    msg.url = (context.env.get('SAP_BRIDGE_URL') || 'http://sap-bridge:8000') + '/api/v1/outbox/' + outboxId + '/update';
    msg.payload = {
        status: 'FAILED',
        last_error: 'HTTP ' + statusCode
    };
    msg._success = false;
    msg._status_code = statusCode;
    node.status({fill:'yellow', shape:'dot', text:'retry #' + outboxId});
    node.warn('[OUTBOX] Event #' + outboxId + ' failed (HTTP ' + statusCode + '), will retry');
}

return msg;

// 注意：HTTP Request 节点返回后，需要另一个 Function 节点检查 needsDeadletter 字段
// 如果 needsDeadletter=true，则调用 deadletter 节点


// =============================================================================
// 节点 3: outbox_deadletter
// 替换原 require('sqlite3') 直插死信 → HTTP POST sap-bridge
// =============================================================================
/*
// 前置：HTTP Request 节点 (method=POST) 指向:
//   http://sap-bridge:8000/api/v1/outbox/{event_id}/deadletter
//   body: { "error_type": "...", "error_message": "...", "payload": {...} }
*/

const outboxId = msg._outbox_id || 0;

msg.method = 'POST';
msg.url = (context.env.get('SAP_BRIDGE_URL') || 'http://sap-bridge:8000') + '/api/v1/outbox/' + outboxId + '/deadletter';
msg.payload = {
    error_type: 'OUTBOX_RETRY_EXCEEDED',
    error_message: 'Outbox event failed after ' + (msg._retry_count || 5) + ' retries (HTTP ' + (msg._status_code || 'unknown') + ')',
    payload: {
        order_id: msg._order_id,
        event_type: msg._event_type,
        outbox_id: msg._outbox_id
    }
};

node.status({fill:'red', shape:'dot', text:'DLQ #' + outboxId});
node.warn('[OUTBOX] Event #' + outboxId + ' sent to dead letter queue');
return msg;


// =============================================================================
// 节点 4: outbox_http_fail (HTTP 请求本身失败时的兜底)
// 替换原 require('sqlite3') 直更新 → HTTP POST sap-bridge
// =============================================================================

msg._success = false;
msg._status_code = 0;

const outboxId = msg._outbox_id || 0;

// 调用 sap-bridge 更新重试计数
msg.method = 'POST';
msg.url = (context.env.get('SAP_BRIDGE_URL') || 'http://sap-bridge:8000') + '/api/v1/outbox/' + outboxId + '/update';
msg.payload = {
    status: 'FAILED',
    last_error: 'HTTP request error (network/timeout)'
};

// HTTP Request 节点返回后检查 needsDeadletter
msg._deadletter_check = true;

node.warn('[OUTBOX] Event #' + outboxId + ' HTTP error, will retry');
return msg;
