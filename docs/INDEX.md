# Documentation Index v3.4

> Master index of all project documentation.

## Quick Start

| Document | Path | Audience |
|----------|------|----------|
| Project Overview | `README.md` | Everyone |
| Development Plan | `PLAN.md` | Developers |
| Project Context | `PROJECT_CONTEXT.md` | AI Assistants |
| Session Status | `SESSION_STATUS.md` | Team |

## Architecture

| Document | Path |
|----------|------|
| Architecture Overview | `01_architecture/` |
| Network Topology | `01_architecture/diagrams/network-topology.md` |
| Architecture Decision Records | `10_adr/` |
| System Architecture (Mermaid) | `CODEBASE OVERVIEW/` |

## Deployment

| Document | Path |
|----------|------|
| Deployment Guide | `02_deployment/` |
| Environments | `02_deployment/environments/` |
| Pre-deployment Checklists | `02_deployment/checklists/` |
| Troubleshooting | `02_deployment/troubleshooting/` |

## Operations

| Document | Path |
|----------|------|
| Runbooks | `03_operations/` |
| Volume Backup Runbook | `03_operations/runbooks/volume-backup.md` |
| Backup Script | `scripts/backup-volumes.sh` |
| Restore Script | `scripts/restore-volumes.sh` |
| Backup Scheduler | `scripts/setup-backup-schedule.ps1` |

## Development

| Document | Path |
|----------|------|
| Development Guide | `04_development/` |
| Monitoring Access Guide | `04_development/monitoring-access-guide.md` |
| IDE Setup | `IDE_SETUP_GUIDE.md` |
| Memory System | `MEMORY_SYSTEM_GUIDE.md` |

## Monitoring

| Document | Path |
|----------|------|
| Prometheus Config | `monitoring/prometheus.yml` |
| Alert Rules | `monitoring/alerts/robot-platform.yml` |
| Grafana Dashboard | `monitoring/grafana-dashboard.json` |
| Alertmanager Config | `monitoring/alertmanager.yml` |
| Monitoring Access Guide | `04_development/monitoring-access-guide.md` |

## Reference

| Document | Path |
|----------|------|
| NTP Clock Sync | `docs/APPENDIX_NTP.md` |
| Notification Config | `docs/APPENDIX_NOTIFICATION.md` |
| Disaster Recovery | `docs/APPENDIX_BACKUP.md` |
| Secrets Management | `docs/secrets-management.md` |
| Troubleshooting | `07_troubleshooting/` |

## Codebase

| Module | Path |
|--------|------|
| SAP Bridge (Python) | `sap-bridge/` |
| Node-RED Flows | `nodered/flows.json` |
| Dashboard (React TS) | `dashboard/src/` |
| Watchdog (Python) | `watchdog/watchdog.py` |
| Simulators (Python) | `sap-bridge/simulators/` |

## Meetings

| Document | Path |
|----------|------|
| Meeting Notes | `06_meetings/` |

## CI/CD

| Document | Path |
|----------|------|
| GitHub CI | `.github/workflows/ci.yml` |
| Security Scan | `.github/workflows/security-scan.yml` |
