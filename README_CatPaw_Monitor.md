# CatPaw Process Monitor

Automated monitoring and auto-restart system for CatPaw processes on Windows.

## Overview

This system monitors your CatPaw processes and automatically restarts them if they crash or become unresponsive. It's designed for Windows 10/11 environments and includes:

1. **Process Monitoring**: Checks if processes are running
2. **Health Checks**: HTTP endpoint verification
3. **Auto-Restart**: Automatic restart on failure
4. **Logging**: Comprehensive logging with rotation
5. **Windows Integration**: Task Scheduler and startup integration

## Quick Start

### Option 1: Quick Setup (Automatic)
```batch
cd "D:\EWM Robot\Robotic Platform Codes"
setup_catpaw_monitor.bat
```

### Option 2: Manual Setup
1. Install Python packages:
   ```batch
   pip install psutil requests
   ```

2. Test the monitor:
   ```batch
   python monitor_catpaw.py --once
   ```

3. Start monitoring:
   ```batch
   python monitor_catpaw.py
   ```

## Configuration

Edit `catpaw_monitor_config.json` to customize:

### Processes to Monitor
```json
{
  "name": "process_name",
  "command": "python -m module.main",
  "working_dir": "C:\\path\\to\\working\\dir",
  "health_check_url": "http://localhost:8080/health",
  "health_check_timeout": 5,
  "restart_delay": 10,
  "max_restarts_per_hour": 5,
  "environment": {
    "VAR1": "value1",
    "VAR2": "value2"
  }
}
```

### Monitoring Settings
```json
"monitoring": {
  "check_interval": 30,      // Seconds between checks
  "log_level": "INFO",       // DEBUG, INFO, WARNING, ERROR
  "log_file": "catpaw_monitor.log",
  "max_log_size_mb": 10,     // Log rotation size
  "backup_count": 5,         // Number of backup logs
  "enable_http_check": true,
  "enable_process_check": true
}
```

## Windows Integration

### Task Scheduler (Recommended for Production)
```powershell
# Run as Administrator in PowerShell
schtasks /create /xml "catpaw_monitor_task.xml" /tn "CatPawMonitor"
```

### Manual Startup Folder
The setup script creates a shortcut in:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

### Service Installation (Alternative)
```batch
# Install as Windows Service (requires pywin32)
pip install pywin32
python monitor_catpaw.py install
```

## Usage

### Start Monitoring
```batch
python monitor_catpaw.py
```

### Run Once (Health Check)
```batch
python monitor_catpaw.py --once
```

### Restart All Processes
```batch
restart_catpaw.bat
```

### Create Windows Task
```batch
python monitor_catpaw.py --create-task
```

### Create Restart Script
```batch
python monitor_catpaw.py --create-restart-script
```

## Features

### Health Monitoring
- Process existence checks (via PID)
- HTTP health checks (for web services)
- Custom health check commands
- Multiple health check types per process

### Auto-Restart
- Configurable restart delay
- Restart limits (per hour)
- Exponential backoff for frequent crashes
- Graceful shutdown support

### Logging & Alerts
- Rotating log files
- Console output
- Email notifications (configurable)
- Slack/Teams/Discord webhooks
- Alert file for external monitoring

### Advanced Features
- Heartbeat monitoring
- Metrics endpoint (Prometheus compatible)
- Web interface (optional)
- Remote monitoring
- Auto-config reload

## Integration with SAP EWM Robot Platform

The monitor is pre-configured for:

1. **CatPaw Main Process** (`catpaw_main`)
2. **SAP Bridge** (`sap_bridge`)
3. **Node-RED** (`node_red`)
4. **Redis** (`redis`)
5. **PostgreSQL** (`postgres`)

### Customizing for Your Setup

1. Update paths in `catpaw_monitor_config.json`
2. Adjust health check URLs/ports
3. Modify restart delays based on process startup time
4. Add environment variables as needed

## Troubleshooting

### Monitor Won't Start
- Check Python installation: `python --version`
- Install required packages: `pip install psutil requests`
- Check file permissions

### Processes Not Being Detected
- Verify process names match the actual commands
- Check if processes are running under different users
- Try using full paths in commands

### Health Checks Failing
- Verify health endpoints are accessible
- Adjust `health_check_timeout` values
- Disable HTTP checks if not needed: `"enable_http_check": false`

### High CPU Usage
- Increase `check_interval` (default: 30 seconds)
- Disable unused health checks
- Reduce number of monitored processes

## Log Files

- `catpaw_monitor.log` - Main monitor logs
- `catpaw_alerts.log` - Alert notifications
- `catpaw_heartbeat.txt` - Last heartbeat timestamp

## Maintenance

### Updating Configuration
```batch
# Stop monitor
Ctrl+C in monitor window

# Edit config
notepad catpaw_monitor_config.json

# Restart monitor
python monitor_catpaw.py
```

### Viewing Logs
```batch
# Tail logs (PowerShell)
Get-Content catpaw_monitor.log -Tail 100 -Wait

# Search for errors
Select-String -Path catpaw_monitor.log -Pattern "ERROR"

# Monitor specific process
Select-String -Path catpaw_monitor.log -Pattern "catpaw_main"
```

### Performance Monitoring
Check monitor resource usage:
```batch
# PowerShell
Get-Process python | Where-Object {$_.CommandLine -like "*monitor_catpaw*"}
```

## Security Considerations

1. **Credentials**: Store passwords in environment variables or Docker secrets
2. **Permissions**: Run with appropriate user permissions
3. **Network**: Health check URLs should be localhost or internal network only
4. **Logs**: Regularly review logs for security events
5. **Updates**: Keep Python packages updated

## Backup and Recovery

### Backup Configuration
```batch
# Backup config
copy catpaw_monitor_config.json catpaw_monitor_config.json.backup

# Backup logs (optional)
compress-archive catpaw_monitor.log,catpaw_alerts.log logs_backup.zip
```

### Restore
```batch
# Restore config
copy catpaw_monitor_config.json.backup catpaw_monitor_config.json

# Restart monitor
python monitor_catpaw.py
```

## Support

For issues:
1. Check logs: `catpaw_monitor.log`
2. Verify configuration: `catpaw_monitor_config.json`
3. Test health checks manually
4. Contact: [Your support contact]

## Changelog

### v1.0.0 (Initial Release)
- Process monitoring with PID tracking
- HTTP health checks
- Auto-restart with configurable delays
- Windows Task Scheduler integration
- Logging with rotation
- Email and webhook notifications

---

**Note**: This monitor is part of the SAP EWM Robot Platform v4.1
Ensure compliance with project standards and iron rules.