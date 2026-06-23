---
name: schema-migration-automation
description: SQLite schema migration automation — versioned migration files, auto-execution on deploy, migration tracking table
---

# Schema 迁移自动化

## 流程
1. 创建 `sql/migrations/NNNN_description.sql`
2. 部署时 `sqlite-init` 容器扫描目录自动执行
3. 迁移文件只追加不修改（不可逆）

## 迁移示例
```sql
-- 0001_add_index.sql
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
```

## 版本追踪
- `sql/migrations/.gitkeep` 保证目录存在
- 已执行迁移记录在 `_migrations` 表（自动创建）
