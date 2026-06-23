# Data_Mask Function Node Reference v1.0

> Wire this before all outbound HTTP Request nodes to prevent sensitive data leaks.
> Design doc: v3.35 §二 (数据脱敏网关), §8.4

## Placement

```
[any previous node] → [Data_Mask Function] → [HTTP Request / MQTT out]
```

- Inbound: `msg.payload` (object with potential sensitive fields)
- Outbound: `msg.payload` (masked) + `msg.payload_original` (audit trail)

## Function Node Code (paste into Node-RED Function node)

```javascript
// ============================================================================
// Data_Mask — 数据脱敏网关 v1.0
// Three strategies: redact / hash / truncate
// Rules stored in SQLite (data_mask_rules table), hot-reloaded every 60s
// Original payload preserved in msg.payload_original for internal audit
// ============================================================================
const crypto = require('crypto');
const CACHE_TTL_MS = 60_000;           // Hot-reload interval
const DB_PATH = process.env.DB_PATH || '/data/robot_platform.db';

// ── Mask engine ────────────────────────────────────────────────────────────
function maskValue(value, type) {
    switch (type) {
        case 'redact':   return '[REDACTED]';
        case 'hash':     return crypto.createHash('sha256')
                            .update(String(value))
                            .digest('hex')
                            .substring(0, 8);
        case 'truncate': {
            const s = String(value);
            return s.length <= 1 ? s : s[0] + '***';
        }
        default:         return '[REDACTED]';
    }
}

// ── Recursive walker ───────────────────────────────────────────────────────
function recursiveMask(obj, rules) {
    if (typeof obj !== 'object' || obj === null) return obj;
    if (Array.isArray(obj)) return obj.map(item => recursiveMask(item, rules));

    const result = {};
    for (const [key, value] of Object.entries(obj)) {
        const rule = rules.find(r =>
            key.toLowerCase().includes(r.field_pattern.toLowerCase())
        );
        if (rule && rule.enabled !== 0) {
            result[key] = maskValue(value, rule.mask_type);
        } else if (typeof value === 'object' && value !== null) {
            result[key] = recursiveMask(value, rules);
        } else {
            result[key] = value;
        }
    }
    return result;
}

// ── Load rules from SQLite (cached with TTL) ──────────────────────────────
function loadRules() {
    const cache = global.get('data_mask_cache');
    const now = Date.now();

    if (cache && (now - cache.ts < CACHE_TTL_MS)) {
        return cache.rules;                   // Hot cache hit
    }

    // Cold — query SQLite
    const sqlite3 = global.get('sqlite3');     // Requires sqlite3 node installed
    let rules = [];

    if (typeof sqlite3 !== 'undefined' && sqlite3 !== null) {
        try {
            const db = sqlite3.open(DB_PATH);
            const rows = db.query(
                "SELECT field_pattern, mask_type, enabled FROM data_mask_rules WHERE enabled = 1"
            );
            if (Array.isArray(rows)) {
                rules = rows;
                node.warn(`[Data_Mask] Loaded ${rules.length} rules from SQLite`);
            }
            db.close();
        } catch (e) {
            node.warn(`[Data_Mask] SQLite read failed, using built-in defaults: ${e.message}`);
        }
    } else {
        node.warn('[Data_Mask] sqlite3 not available, using built-in defaults');
    }

    // Fallback: built-in defaults (match migration 002)
    if (rules.length === 0) {
        rules = [
            { field_pattern: 'password',  mask_type: 'redact',   enabled: 1 },
            { field_pattern: 'passwd',    mask_type: 'redact',   enabled: 1 },
            { field_pattern: 'token',     mask_type: 'redact',   enabled: 1 },
            { field_pattern: 'secret',    mask_type: 'redact',   enabled: 1 },
            { field_pattern: 'api_key',   mask_type: 'redact',   enabled: 1 },
            { field_pattern: 'phone',     mask_type: 'redact',   enabled: 1 },
            { field_pattern: 'sap_user',  mask_type: 'hash',     enabled: 1 },
            { field_pattern: 'operator',  mask_type: 'truncate', enabled: 1 },
            { field_pattern: 'email',     mask_type: 'truncate', enabled: 1 },
        ];
        node.warn('[Data_Mask] Using 9 built-in default rules');
    }

    // Update cache
    global.set('data_mask_cache', { rules, ts: now });
    return rules;
}

// ── Main ───────────────────────────────────────────────────────────────────
const rules = loadRules();

// Preserve original for internal audit trail
msg.payload_original = JSON.parse(JSON.stringify(msg.payload));

// Apply mask
msg.payload = recursiveMask(msg.payload, rules);

// Count what was masked
const maskedCount = (function countMasked(original, masked) {
    if (typeof original !== 'object' || original === null) return 0;
    let count = 0;
    for (const k of Object.keys(original)) {
        if (typeof original[k] === 'object' && original[k] !== null) {
            count += countMasked(original[k], masked?.[k]);
        } else if (masked?.[k] === '[REDACTED]' ||
                   (masked?.[k] && typeof masked[k] === 'string' &&
                    masked[k].includes('***'))) {
            count++;
        }
    }
    return count;
})(msg.payload_original, msg.payload);

if (maskedCount > 0) {
    node.warn(`[Data_Mask] Masked ${maskedCount} sensitive field(s)`);
}

return msg;
```

## Configuration

1. Install Node-RED node: `node-red-contrib-sqlite` (for DB queries)
2. Add to `settings.js`:
   ```js
   process.env.DB_PATH = '/data/robot_platform.db';
   ```
3. Wire this Function node before all outbound HTTP/MQTT nodes
4. Restart Node-RED once

## Rule Hot-Reload

Rules live in SQLite `data_mask_rules` table. Update without restart:

```sql
-- Disable a rule
UPDATE data_mask_rules SET enabled = 0, updated_at = datetime('now')
WHERE field_pattern = 'operator';

-- Add a custom rule
INSERT INTO data_mask_rules (field_pattern, mask_type, description)
VALUES ('credit_card', 'redact', 'PCI-DSS compliance');

-- Verify
SELECT * FROM data_mask_rules WHERE enabled = 1;
```

Changes take effect within 60 seconds (CACHE_TTL_MS). No Node-RED restart needed.

## Testing

```bash
# Expected: password → [REDACTED], operator → Z***, sap_user → a1b2c3d4
curl -X POST http://nodered:1880/api/test-mask \
  -H "Content-Type: application/json" \
  -d '{"user":"admin","password":"s3cret!","operator":"Zhang Wei","sap_user":"SAP_EWM_01"}'
```
