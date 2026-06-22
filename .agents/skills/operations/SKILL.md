---
name: operations
description: Operations and deployment guidance for production systems. Use when deploying applications, managing infrastructure, monitoring systems, handling incidents, or performing operational tasks.
---

# Operations Guide

## Overview

This skill provides operational guidance for:
- Deploying applications to production
- Managing infrastructure and services
- Monitoring system health and performance
- Handling incidents and emergencies
- Performing maintenance tasks

## When to Use

- Deploying new versions or updates
- Setting up monitoring and alerting
- Responding to incidents or outages
- Performing database migrations
- Scaling infrastructure
- Troubleshooting production issues

## Deployment Practices

### 1. **Pre-Deployment Checklist**
- All tests passing (unit, integration, e2e)
- Code reviewed and approved
- Database migrations tested in staging
- Rollback plan documented
- Monitoring and alerting configured
- Stakeholders notified (if impactful)

### 2. **Deployment Strategy**
- Use blue-green or canary deployments when possible
- Deploy during low-traffic periods for risky changes
- Monitor closely for first 30 minutes post-deploy
- Have rollback procedures ready
- Document deployment steps and outcomes

### 3. **Database Migrations**
- Test migrations on copy of production data
- Make migrations backward compatible
- Deploy schema changes separately from code changes
- Have rollback migration ready
- Monitor migration performance on production

## Monitoring & Alerting

### Key Metrics to Monitor
- **Availability**: Uptime, error rates, health checks
- **Performance**: Response times, throughput, latency percentiles
- **Resources**: CPU, memory, disk, network utilization
- **Business**: User activity, transaction volumes, conversion rates

### Alert Configuration
- Alert on symptoms, not causes
- Set appropriate thresholds (avoid alert fatigue)
- Include runbook links in alerts
- Test alert delivery regularly
- Review and tune alerts quarterly

## Incident Response

### 1. **Detection**
- Automated monitoring alerts
- User reports
- Anomaly detection
- Log analysis

### 2. **Response Process**
- Acknowledge the incident immediately
- Assess impact and severity
- Communicate to stakeholders
- Investigate root cause
- Apply fix or workaround
- Verify resolution
- Conduct post-mortem

### 3. **Post-Mortem**
- Document timeline of events
- Identify root cause(s)
- List action items to prevent recurrence
- Assign owners and deadlines
- Share learnings with team

## Infrastructure Management

### Best Practices
- Infrastructure as Code (IaC) for reproducibility
- Immutable infrastructure when possible
- Regular security patches and updates
- Backup and disaster recovery testing
- Document all operational procedures

### Common Operations
- **Scaling**: Horizontal vs vertical, auto-scaling policies
- **Backups**: Automated, tested, off-site storage
- **Secrets Management**: Vault, environment variables, rotation
- **Log Management**: Centralized logging, retention policies
- **Certificate Management**: Auto-renewal, monitoring expiry

## Troubleshooting

### Systematic Approach
1. **Reproduce**: Can you reproduce the issue?
2. **Isolate**: What component is failing?
3. **Analyze**: Check logs, metrics, recent changes
4. **Hypothesize**: What could cause this?
5. **Test**: Validate your hypothesis
6. **Fix**: Apply and verify the fix
7. **Document**: Record the issue and solution

### Essential Commands
- Check service status: `systemctl status <service>`
- View logs: `journalctl -u <service> -f`
- Check resources: `top`, `htop`, `df -h`, `free -m`
- Network diagnostics: `curl`, `ping`, `nslookup`, `traceroute`
- Process inspection: `ps aux`, `lsof`, `strace`

## Security Operations

- Regular vulnerability scanning
- Dependency updates and patching
- Access control review (least privilege)
- Audit logging enabled
- Incident response plan tested
- Security training for team
