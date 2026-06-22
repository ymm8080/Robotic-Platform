---
name: disaster-recovery
description: Disaster recovery for EWM Robotic Platform 7.2 DR manual, backup strategies, failover mechanisms, DR drills, RTO/RPO objectives.
---

# Disaster Recovery

Disaster recovery implementation for EWM Robotic Platform 7.2 DR manual.

## When to Use
- Implementing 7.2 disaster recovery manual
- Creating backup scripts for PostgreSQL, Redis, MQTT
- Designing active-passive failover with Keepalived VIP
- Writing DR runbooks for catastrophic failure scenarios
- Scheduling automated DR drills

## Activation Triggers
> "Create PostgreSQL backup script with daily full backup and WAL archiving"
> "Implement active-passive failover for SAP bridge with Keepalived VIP"
> "Write disaster recovery runbook for complete database loss scenario"
> "Set up automated DR drill schedule with monthly database restore tests"

## EWM DR Requirements
- **RTO**: SAP bridge 15min, Redis 10min, PostgreSQL 30min
- **RPO**: SAP bridge 1min, PostgreSQL 1min, Redis 5min
- **Backups**: PostgreSQL (daily + WAL), Redis (RDB + AOF), MQTT (archiver)
- **Failover**: Keepalived VIP, active-passive SAP bridge
- **DR Drills**: Monthly DB restore, quarterly failover, semi-annual full DR
- **Remote storage**: S3/MinIO for offsite backup retention (30 days)

## Critical Preconditions (Merged into Global Rules)
> These are now enforced automatically by 000-global-iron-rules:
> - All Redis/PostgreSQL must have persistence (AOF/RDB) + host Volume
> - Docker Compose upgrades must auto-backup config + .env first
> - MQTT Broker changes must leave rollback snapshots in ops/backup/
