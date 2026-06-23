-- Migration 001: Extend orders table with missing fields from PLAN.md §2.2.1
-- Adds: type, priority, source, robot_brand, robot_serial, payload, completed_at
-- Prerequisite: init.sql (base schema)

PRAGMA journal_mode=WAL;
BEGIN TRANSACTION;

-- Create the extended orders table
CREATE TABLE IF NOT EXISTS orders_v2 (
    id INTEGER PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'MOVE'
        CHECK(type IN ('PICK', 'PUT', 'MOVE', 'CHARGE')),
    priority INTEGER NOT NULL DEFAULT 3
        CHECK(priority >= 0 AND priority <= 3),
    source TEXT,                    -- SAP warehouse task ID
    robot_brand TEXT,
    robot_serial TEXT,
    status TEXT NOT NULL DEFAULT 'CREATED'
        CHECK(status IN (
            'CREATED', 'ASSIGNED', 'IN_PROGRESS',
            'COMPLETED', 'FAILED', 'CANCELLED',
            'SUSPENDED', 'DIFF_SUSPENDED'
        )),
    payload TEXT,                   -- VDA5050 order payload (JSON)
    zone_id TEXT,
    zone_token TEXT,
    weight REAL,
    location TEXT,
    env_tag TEXT DEFAULT 'PROD',
    expected_qty INTEGER,
    assigned_rule_id INTEGER,
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    version INTEGER DEFAULT 1
);

-- Copy data from old orders table if it exists
INSERT OR IGNORE INTO orders_v2 (
    id, order_no, status, robot_brand, zone_id, zone_token,
    weight, location, env_tag, expected_qty, assigned_rule_id,
    created_at, updated_at, version
)
SELECT
    id, order_no, status, brand, zone_id, zone_token,
    weight, location, env_tag, expected_qty, assigned_rule_id,
    created_at, updated_at, version
FROM orders;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_orders_v2_status ON orders_v2(status);
CREATE INDEX IF NOT EXISTS idx_orders_v2_type ON orders_v2(type);
CREATE INDEX IF NOT EXISTS idx_orders_v2_priority ON orders_v2(priority);
CREATE INDEX IF NOT EXISTS idx_orders_v2_robot ON orders_v2(robot_brand, robot_serial);
CREATE INDEX IF NOT EXISTS idx_orders_v2_source ON orders_v2(source);
CREATE INDEX IF NOT EXISTS idx_orders_v2_created ON orders_v2(created_at);

-- Version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now')),
    description TEXT
);

INSERT INTO schema_version (version, description)
VALUES (2, 'Extended orders table: type, priority, source, robot_brand, robot_serial, payload, completed_at');

COMMIT;
