-- =============================================================================
-- SAP-EWM Robot Dispatch Platform — PostgreSQL Schema v1.0
-- Target: PostgreSQL 15+
-- Migration from: SQLite (see scripts/data-migration-sqlite-to-pg.sh)
-- =============================================================================

-- WAL-style settings (PG equivalent of SQLite WAL mode)
SET synchronous_commit = on;

-- =============================================================================
-- Core Tables
-- =============================================================================

-- Orders table (evolution of SQLite orders_v2)
CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    order_no        TEXT NOT NULL UNIQUE,
    type            TEXT NOT NULL DEFAULT 'MOVE'
                        CHECK(type IN ('PICK', 'PUT', 'MOVE', 'CHARGE')),
    priority        INTEGER NOT NULL DEFAULT 3
                        CHECK(priority >= 0 AND priority <= 3),
    source          TEXT,                           -- SAP warehouse task ID
    robot_brand     TEXT,
    robot_serial    TEXT,
    status          TEXT NOT NULL DEFAULT 'CREATED'
                        CHECK(status IN (
                            'CREATED', 'ASSIGNED', 'IN_PROGRESS',
                            'COMPLETED', 'FAILED', 'CANCELLED',
                            'SUSPENDED', 'DIFF_SUSPENDED'
                        )),
    payload         JSONB,                          -- VDA5050 order payload
    zone_id         TEXT,
    zone_token      TEXT,
    weight          NUMERIC(10, 2),
    location        TEXT,
    env_tag         TEXT DEFAULT 'PROD',
    expected_qty    INTEGER,
    assigned_rule_id INTEGER,
    error_message   TEXT,
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_type ON orders(type);
CREATE INDEX IF NOT EXISTS idx_orders_priority ON orders(priority);
CREATE INDEX IF NOT EXISTS idx_orders_robot ON orders(robot_brand, robot_serial);
CREATE INDEX IF NOT EXISTS idx_orders_source ON orders(source);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

-- Outbox events (Saga pattern)
CREATE TABLE IF NOT EXISTS outbox_events (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB,
    status          TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK(status IN ('PENDING', 'SENT', 'FAILED')),
    retry_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at         TIMESTAMPTZ,
    last_error      TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_events(status);
CREATE INDEX IF NOT EXISTS idx_outbox_order ON outbox_events(order_id);

-- Audit log (6-month retention per 等保)
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event           TEXT NOT NULL,
    "user"          TEXT,
    path            TEXT,
    type            TEXT,
    message         TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

-- Dead letter queue
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id              SERIAL PRIMARY KEY,
    original_id     TEXT,
    error_type      TEXT,
    error_message   TEXT,
    payload         JSONB,
    status          TEXT NOT NULL DEFAULT 'UNRESOLVED'
                        CHECK(status IN ('UNRESOLVED', 'RESOLVED', 'RETRIED')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolution      TEXT
);

-- Zone locks (cross-brand collision prevention)
CREATE TABLE IF NOT EXISTS zone_lock (
    zone_id         TEXT PRIMARY KEY,
    robot_id        TEXT NOT NULL,
    brand           TEXT,
    zone_token      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

-- Robot status
CREATE TABLE IF NOT EXISTS robot_status (
    robot_id        TEXT PRIMARY KEY,
    brand           TEXT,
    status          TEXT NOT NULL DEFAULT 'OFFLINE'
                        CHECK(status IN (
                            'ONLINE', 'OFFLINE', 'BUSY', 'ERROR', 'CHARGING'
                        )),
    battery         INTEGER DEFAULT 0,
    position        JSONB,
    env_tag         TEXT DEFAULT 'PROD',
    last_heartbeat  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_robot_status_env ON robot_status(status, env_tag);

-- API deviation log (vendor accountability)
CREATE TABLE IF NOT EXISTS api_deviation_log (
    id              SERIAL PRIMARY KEY,
    brand           TEXT,
    api_version     TEXT,
    error_type      TEXT,
    expected_response JSONB,
    actual_response JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dispatch rules (grayscale support)
CREATE TABLE IF NOT EXISTS dispatch_rules (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    rule_config     JSONB NOT NULL,
    effective_from  TIMESTAMPTZ,
    effective_to    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Data mask rules (hot-reloadable)
CREATE TABLE IF NOT EXISTS data_mask_rules (
    id              SERIAL PRIMARY KEY,
    field_pattern   TEXT NOT NULL,
    mask_type       TEXT NOT NULL CHECK(mask_type IN ('redact', 'hash', 'truncate')),
    description     TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_mask_pattern ON data_mask_rules(field_pattern);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version         INTEGER PRIMARY KEY,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description     TEXT
);

-- =============================================================================
-- Constraints & Triggers
-- =============================================================================

-- 等保合规：禁止清理 180 天内审计日志
CREATE OR REPLACE FUNCTION trg_audit_log_protect_fn()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.timestamp > NOW() - INTERVAL '180 days' THEN
        RAISE EXCEPTION '等保合规：180 天内数据禁止清理';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_log_protect
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION trg_audit_log_protect_fn();

-- 等保合规：禁止清理 180 天内订单
CREATE OR REPLACE FUNCTION trg_orders_protect_fn()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.created_at > NOW() - INTERVAL '180 days' THEN
        RAISE EXCEPTION '等保合规：180 天内数据禁止清理';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orders_protect
    BEFORE DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION trg_orders_protect_fn();

-- Auto-update updated_at on orders
CREATE OR REPLACE FUNCTION trg_orders_updated_at_fn()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION trg_orders_updated_at_fn();

-- =============================================================================
-- Seed Data
-- =============================================================================

-- Default data mask rules
INSERT INTO data_mask_rules (field_pattern, mask_type, description) VALUES
    ('password', 'redact',  'SAP / Dify / MQTT passwords — full redaction'),
    ('passwd',   'redact',  'Linux / mosquitto password files'),
    ('token',    'redact',  'Auth tokens, zone tokens, API tokens'),
    ('secret',   'redact',  'Webhook secrets, app secrets'),
    ('api_key',  'redact',  'Third-party API keys'),
    ('phone',    'redact',  'Operator phone numbers — full redaction'),
    ('sap_user', 'hash',    'SAP usernames — SHA256 prefix (8 chars)'),
    ('operator', 'truncate','Operator names — show first char only'),
    ('email',    'truncate','Email addresses — show first char only')
ON CONFLICT DO NOTHING;

-- Schema version
INSERT INTO schema_version (version, description)
VALUES (4, 'PostgreSQL v1.0: full platform schema migrated from SQLite')
ON CONFLICT DO NOTHING;
