-- Migration 002: Data Mask Gateway — sensitive field redaction
-- Adds: data_mask_rules table with default rules
-- Prerequisite: init.sql (base schema)
-- Hot-reload: Node-RED Function node queries this table on each call
--              (with 60s in-memory cache, no restart needed for rule changes)

PRAGMA journal_mode=WAL;
BEGIN TRANSACTION;

-- Data masking rules table (hot-reloadable)
CREATE TABLE IF NOT EXISTS data_mask_rules (
    id INTEGER PRIMARY KEY,
    field_pattern TEXT NOT NULL,       -- case-insensitive substring match against field name
    mask_type TEXT NOT NULL            -- 'redact' | 'hash' | 'truncate'
        CHECK(mask_type IN ('redact', 'hash', 'truncate')),
    description TEXT,                   -- human-readable: what this rule protects
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Default rules (v3.35 design document §8.4)
INSERT INTO data_mask_rules (field_pattern, mask_type, description) VALUES
    ('password', 'redact',  'SAP / Dify / MQTT passwords — full redaction'),
    ('passwd',   'redact',  'Linux / mosquitto password files'),
    ('token',    'redact',  'Auth tokens, zone tokens, API tokens'),
    ('secret',   'redact',  'Webhook secrets, app secrets'),
    ('api_key',  'redact',  'Third-party API keys'),
    ('phone',    'redact',  'Operator phone numbers — full redaction'),
    ('sap_user', 'hash',    'SAP usernames — SHA256 prefix (8 chars)'),
    ('operator', 'truncate','Operator names — show first char only'),
    ('email',    'truncate','Email addresses — show first char only');

CREATE INDEX IF NOT EXISTS idx_data_mask_pattern ON data_mask_rules(field_pattern);

-- Version tracking
INSERT OR IGNORE INTO schema_version (version, description)
VALUES (3, 'Data mask gateway: data_mask_rules table with 9 default rules');

COMMIT;
