-- =============================================================================
-- SAP-EWM 消息网关数据库初始化 (v3.5 新增)
-- 数据库：PostgreSQL (与核心业务共享实例) 或 SQLite (开发模式)
-- 此脚本创建消息网关所需的表结构
-- =============================================================================

-- 审计日志表（所有经过网关的操作记录）
CREATE TABLE IF NOT EXISTS gateway_audit_log (
    log_id          TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,  -- ISO 8601 UTC
    operator        TEXT NOT NULL,  -- 系统用户ID
    operator_name   TEXT DEFAULT '',
    platform        TEXT NOT NULL,  -- wechat/feishu/dingtalk/email/internal
    action_type     TEXT NOT NULL,  -- robot_stop/order_cancel/robot_recall/zone_lock/...
    target_id       TEXT NOT NULL,
    target_type     TEXT NOT NULL,  -- robot/order/zone
    execution_id    TEXT DEFAULT '',
    status          TEXT NOT NULL,  -- INIT/NOTIFIED/CONFIRMING/CONFIRMED/EXECUTING/SUCCESS/FAILED/TIMEOUT/CANCELLED
    detail          TEXT DEFAULT '{}',  -- JSON
    ip_address      TEXT DEFAULT '',
    user_agent      TEXT DEFAULT '',
    is_critical     INTEGER DEFAULT 0,  -- 0=no, 1=yes (WORM backup required)
    correlation_id  TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 索引：按时间范围查询
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON gateway_audit_log(timestamp);
-- 索引：按操作人查询
CREATE INDEX IF NOT EXISTS idx_audit_operator ON gateway_audit_log(operator);
-- 索引：按操作类型查询
CREATE INDEX IF NOT EXISTS idx_audit_action_type ON gateway_audit_log(action_type);
-- 索引：按目标对象查询
CREATE INDEX IF NOT EXISTS idx_audit_target ON gateway_audit_log(target_id);
-- 索引：按执行ID查询
CREATE INDEX IF NOT EXISTS idx_audit_exec_id ON gateway_audit_log(execution_id);

-- 用户绑定表（平台用户与系统用户映射）
CREATE TABLE IF NOT EXISTS gateway_user_bindings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,          -- wechat/feishu/dingtalk
    platform_user_id TEXT NOT NULL,         -- 平台侧用户ID
    platform_user_name TEXT DEFAULT '',
    bound_user_id   TEXT NOT NULL,          -- 系统用户ID
    bound_at        TEXT DEFAULT (datetime('now')),
    bound_by        TEXT DEFAULT '',        -- 操作人
    status          TEXT DEFAULT 'active',  -- active/disabled
    UNIQUE(platform, platform_user_id)
);

-- 索引：按平台+用户ID查询
CREATE INDEX IF NOT EXISTS idx_binding_platform_user ON gateway_user_bindings(platform, platform_user_id);
-- 索引：按系统用户ID查询
CREATE INDEX IF NOT EXISTS idx_binding_bound_user ON gateway_user_bindings(bound_user_id);

-- 渠道配置表（各平台的通知配置）
CREATE TABLE IF NOT EXISTS gateway_channel_configs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT NOT NULL UNIQUE,   -- wechat/feishu/dingtalk/email
    enabled         INTEGER DEFAULT 0,      -- 0=disabled, 1=enabled
    priority_order  INTEGER DEFAULT 0,      -- 优先级排序
    config          TEXT DEFAULT '{}',      -- JSON: 平台特定配置
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- 操作记录表（操作状态机跟踪）
CREATE TABLE IF NOT EXISTS gateway_operations (
    execution_id    TEXT PRIMARY KEY,
    notification_id TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'INIT',  -- INIT/NOTIFIED/CONFIRMING/CONFIRMED/EXECUTING/SUCCESS/FAILED/TIMEOUT/CANCELLED
    action_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    target_type     TEXT NOT NULL,
    operator        TEXT DEFAULT '',
    operator_name   TEXT DEFAULT '',
    platform        TEXT DEFAULT '',
    alert_id        TEXT DEFAULT '',
    correlation_id  TEXT DEFAULT '',
    require_confirm INTEGER DEFAULT 0,
    confirm_token   TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    notified_at     TEXT DEFAULT '',
    confirmed_at    TEXT DEFAULT '',
    executed_at     TEXT DEFAULT '',
    result          TEXT DEFAULT '{}',      -- JSON
    expire_at       TEXT DEFAULT ''
);

-- 索引：按状态查询（查找超时操作）
CREATE INDEX IF NOT EXISTS idx_op_status ON gateway_operations(status);
-- 索引：按告警ID查询
CREATE INDEX IF NOT EXISTS idx_op_alert_id ON gateway_operations(alert_id);
-- 索引：按关联ID查询
CREATE INDEX IF NOT EXISTS idx_op_correlation ON gateway_operations(correlation_id);

-- 权限表（用户操作权限）
CREATE TABLE IF NOT EXISTS gateway_permissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    action_type     TEXT NOT NULL,          -- robot_stop/order_cancel/robot_recall/zone_lock/zone_unlock/*(wildcard)
    granted_by      TEXT DEFAULT '',
    granted_at      TEXT DEFAULT (datetime('now')),
    expires_at      TEXT DEFAULT '',        -- 空=永不过期
    UNIQUE(user_id, action_type)
);

-- 索引：按用户ID查询权限
CREATE INDEX IF NOT EXISTS idx_perm_user ON gateway_permissions(user_id);

-- 数据脱敏规则表（网关侧脱敏，与核心平台同步）
CREATE TABLE IF NOT EXISTS gateway_data_mask_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_pattern   TEXT NOT NULL,          -- 字段名匹配模式
    mask_type       TEXT NOT NULL,          -- redact/hash/truncate
    created_at      TEXT DEFAULT (datetime('now')),
    enabled         INTEGER DEFAULT 1
);

-- 初始化默认渠道配置
INSERT OR IGNORE INTO gateway_channel_configs (channel, enabled, priority_order, config) VALUES
    ('wechat',   0, 1, '{}'),
    ('feishu',   0, 2, '{}'),
    ('dingtalk', 0, 3, '{}'),
    ('email',    0, 4, '{}');

-- 初始化默认脱敏规则
INSERT OR IGNORE INTO gateway_data_mask_rules (field_pattern, mask_type) VALUES
    ('password', 'redact'),
    ('token', 'redact'),
    ('secret', 'redact'),
    ('phone', 'redact'),
    ('email', 'truncate'),
    ('sap_user', 'hash');

-- 版本记录
INSERT OR REPLACE INTO schema_version (version, migration_name) VALUES
    (2, 'v3.5_gateway_init');
