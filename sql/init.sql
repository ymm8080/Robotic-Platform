-- SAP-EWM 机器人调度平台数据库初始化脚本 v3.4
-- 执行方式：sqlite3 robot_platform.db < init.sql

PRAGMA journal_mode=WAL;
PRAGMA wal_autocheckpoint=500;

-- 订单表
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'PENDING',
    robot_id TEXT,
    zone_id TEXT,
    zone_token TEXT,
    weight REAL,
    location TEXT,
    brand TEXT,
    env_tag TEXT DEFAULT 'PROD',
    expected_qty INTEGER,
    assigned_rule_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    version INTEGER DEFAULT 1
);

-- Outbox 事件表（穷人的 Saga）
CREATE TABLE IF NOT EXISTS outbox_events (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT,
    status TEXT DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 审计日志表（等保 6 个月留存）
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT DEFAULT (datetime('now')),
    event TEXT NOT NULL,
    user TEXT,
    path TEXT,
    type TEXT,
    message TEXT
);

-- 死信队列
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id INTEGER PRIMARY KEY,
    original_id INTEGER,
    error_type TEXT,
    error_message TEXT,
    payload TEXT,
    status TEXT DEFAULT 'UNRESOLVED',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 区域锁表
CREATE TABLE IF NOT EXISTS zone_lock (
    zone_id TEXT PRIMARY KEY,
    robot_id TEXT NOT NULL,
    brand TEXT,
    zone_token TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);

-- 机器人状态表
CREATE TABLE IF NOT EXISTS robot_status (
    robot_id TEXT PRIMARY KEY,
    brand TEXT,
    status TEXT DEFAULT 'OFFLINE',
    battery INTEGER,
    position TEXT,
    env_tag TEXT DEFAULT 'PROD',
    last_heartbeat TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- API 偏差日志表（甩锅证据）
CREATE TABLE IF NOT EXISTS api_deviation_log (
    id INTEGER PRIMARY KEY,
    brand TEXT,
    api_version TEXT,
    error_type TEXT,
    expected_response TEXT,
    actual_response TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 调度规则表（支持灰度）
CREATE TABLE IF NOT EXISTS dispatch_rules (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    rule_config TEXT NOT NULL,
    effective_from TEXT,
    effective_to TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_robot ON orders(robot_id);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_events(status);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_robot_status ON robot_status(status);
