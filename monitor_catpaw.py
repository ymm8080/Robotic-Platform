#!/usr/bin/env python3
"""
CatPaw Window Monitor and Auto-Restart System

This script monitors CatPaw processes and automatically restarts them
if they stop running. It includes health checks and logging.

Features:
1. Process monitoring (PID tracking)
2. Automatic restart on failure
3. Health checks before restart
4. Configurable check intervals
5. Logging with rotation
6. Windows service compatible
"""

import os
import sys
import time
import logging
import subprocess
import signal
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
import threading
import socket


class CatPawMonitor:
    """Monitor and auto-restart CatPaw processes."""
    
    def __init__(self, config_file: str = "catpaw_monitor_config.json"):
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.processes: Dict[str, Dict[str, Any]] = {}
        self.stop_event = threading.Event()
        
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        default_config = {
            "processes": [
                {
                    "name": "catpaw_main",
                    "command": "python -m catpaw.main",
                    "working_dir": r"D:\EWM Robot\Robotic Platform Codes",
                    "health_check_url": "http://localhost:8080/health",
                    "health_check_timeout": 5,
                    "restart_delay": 10,
                    "max_restarts_per_hour": 5
                },
                {
                    "name": "sap_bridge",
                    "command": "python -m sap_bridge.main",
                    "working_dir": r"D:\EWM Robot\Robotic Platform Codes\sap-bridge",
                    "health_check_url": "http://localhost:8000/health",
                    "health_check_timeout": 5,
                    "restart_delay": 15,
                    "max_restarts_per_hour": 3
                }
            ],
            "monitoring": {
                "check_interval": 30,
                "log_level": "INFO",
                "log_file": "catpaw_monitor.log",
                "max_log_size_mb": 10,
                "backup_count": 5,
                "enable_http_check": True,
                "enable_process_check": True
            }
        }
        
        config_path = Path(config_file)
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                # Merge with defaults
                merged = default_config.copy()
                merged.update(user_config)
                return merged
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")
                return default_config
        else:
            # Save default config
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"Created default config at {config_path}")
            return default_config
            
    def setup_logging(self):
        """Configure logging with rotation."""
        log_config = self.config["monitoring"]
        log_file = log_config["log_file"]
        max_size = log_config["max_log_size_mb"] * 1024 * 1024
        
        logging.basicConfig(
            level=getattr(logging, log_config["log_level"]),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger("CatPawMonitor")
        
    def is_process_running(self, process_name: str, pid: Optional[int] = None) -> bool:
        """Check if a process is running."""
        try:
            if pid:
                psutil.Process(pid)
                return True
                
            # Search by name
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if process_name in ' '.join(proc.info['cmdline'] or []):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False
        except psutil.NoSuchProcess:
            return False
        except Exception as e:
            self.logger.error(f"Error checking process {process_name}: {e}")
            return False
            
    def check_http_health(self, url: str, timeout: int) -> bool:
        """Perform HTTP health check."""
        import requests
        try:
            response = requests.get(url, timeout=timeout)
            return response.status_code == 200
        except requests.RequestException as e:
            self.logger.debug(f"HTTP health check failed for {url}: {e}")
            return False
        except ImportError:
            self.logger.warning("requests module not available, skipping HTTP check")
            return True  # Assume healthy if we can't check
            
    def start_process(self, process_config: Dict[str, Any]) -> Optional[subprocess.Popen]:
        """Start a process with the given configuration."""
        try:
            cmd = process_config["command"]
            cwd = process_config.get("working_dir")
            env = os.environ.copy()
            
            # Add project-specific environment variables
            env["PYTHONPATH"] = str(Path(r"D:\EWM Robot\Robotic Platform Codes"))
            
            self.logger.info(f"Starting process: {process_config['name']}")
            self.logger.info(f"Command: {cmd}")
            self.logger.info(f"Working dir: {cwd}")
            
            process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start output readers in background threads
            threading.Thread(
                target=self._read_output,
                args=(process_config["name"], process.stdout, "STDOUT"),
                daemon=True
            ).start()
            
            threading.Thread(
                target=self._read_output,
                args=(process_config["name"], process.stderr, "STDERR"),
                daemon=True
            ).start()
            
            return process
            
        except Exception as e:
            self.logger.error(f"Failed to start process {process_config['name']}: {e}")
            return None
            
    def _read_output(self, process_name: str, pipe, stream_name: str):
        """Read and log process output."""
        try:
            for line in iter(pipe.readline, ''):
                if line.strip():
                    self.logger.info(f"[{process_name} {stream_name}] {line.rstrip()}")
        except Exception as e:
            self.logger.debug(f"Error reading {stream_name} for {process_name}: {e}")
            
    def monitor_process(self, process_config: Dict[str, Any]):
        """Monitor and restart a single process."""
        process_name = process_config["name"]
        restart_history = []
        
        while not self.stop_event.is_set():
            try:
                # Check if process exists in our tracking
                if process_name not in self.processes:
                    self.logger.info(f"Starting {process_name} for the first time")
                    proc = self.start_process(process_config)
                    if proc:
                        self.processes[process_name] = {
                            "process": proc,
                            "pid": proc.pid,
                            "start_time": datetime.now(),
                            "restart_count": 0,
                            "last_restart": None
                        }
                    else:
                        self.logger.error(f"Failed to start {process_name}")
                        time.sleep(process_config["restart_delay"])
                        continue
                        
                proc_info = self.processes[process_name]
                proc = proc_info["process"]
                
                # Check if process is still alive
                return_code = proc.poll()
                if return_code is not None:
                    self.logger.warning(
                        f"Process {process_name} (PID: {proc_info['pid']}) "
                        f"exited with code {return_code}"
                    )
                    
                    # Check restart limits
                    now = datetime.now()
                    hour_ago = now - timedelta(hours=1)
                    recent_restarts = [
                        t for t in restart_history 
                        if t > hour_ago
                    ]
                    
                    if len(recent_restarts) >= process_config["max_restarts_per_hour"]:
                        self.logger.error(
                            f"Process {process_name} exceeded restart limit "
                            f"({process_config['max_restarts_per_hour']}/hour). "
                            f"Not restarting."
                        )
                        time.sleep(60)
                        continue
                        
                    # Restart process
                    self.logger.info(f"Restarting {process_name}...")
                    time.sleep(process_config["restart_delay"])
                    
                    new_proc = self.start_process(process_config)
                    if new_proc:
                        self.processes[process_name] = {
                            "process": new_proc,
                            "pid": new_proc.pid,
                            "start_time": datetime.now(),
                            "restart_count": proc_info["restart_count"] + 1,
                            "last_restart": now
                        }
                        restart_history.append(now)
                        # Keep only last 24 hours of restart history
                        restart_history = [
                            t for t in restart_history 
                            if t > now - timedelta(hours=24)
                        ]
                    else:
                        self.logger.error(f"Failed to restart {process_name}")
                        
                # Perform health check
                if self.config["monitoring"]["enable_http_check"]:
                    health_url = process_config.get("health_check_url")
                    if health_url:
                        is_healthy = self.check_http_health(
                            health_url,
                            process_config["health_check_timeout"]
                        )
                        if not is_healthy:
                            self.logger.warning(
                                f"Health check failed for {process_name} at {health_url}"
                            )
                            # Consider restarting if health check fails multiple times
                            
            except Exception as e:
                self.logger.error(f"Error monitoring {process_name}: {e}")
                
            # Wait for next check
            time.sleep(self.config["monitoring"]["check_interval"])
            
    def stop_all_processes(self):
        """Stop all monitored processes."""
        self.logger.info("Stopping all monitored processes...")
        self.stop_event.set()
        
        for process_name, proc_info in self.processes.items():
            try:
                proc = proc_info["process"]
                if proc.poll() is None:  # Process is still running
                    self.logger.info(f"Stopping {process_name} (PID: {proc_info['pid']})")
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.logger.warning(f"Force killing {process_name}")
                        proc.kill()
            except Exception as e:
                self.logger.error(f"Error stopping {process_name}: {e}")
                
    def run(self):
        """Main monitoring loop."""
        self.logger.info("Starting CatPaw Monitor...")
        self.logger.info(f"Monitoring {len(self.config['processes'])} processes")
        
        # Start monitor threads for each process
        monitor_threads = []
        for process_config in self.config["processes"]:
            thread = threading.Thread(
                target=self.monitor_process,
                args=(process_config,),
                daemon=True
            )
            thread.start()
            monitor_threads.append(thread)
            self.logger.info(f"Started monitor for {process_config['name']}")
            
        # Main loop
        try:
            while not self.stop_event.is_set():
                # Log status every 5 minutes
                time.sleep(300)
                self.log_status()
                
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        finally:
            self.stop_all_processes()
            self.logger.info("CatPaw Monitor stopped")
            
    def log_status(self):
        """Log current status of all monitored processes."""
        status_lines = ["=== CatPaw Monitor Status ==="]
        
        for process_name, proc_info in self.processes.items():
            proc = proc_info["process"]
            uptime = datetime.now() - proc_info["start_time"]
            uptime_str = str(uptime).split('.')[0]  # Remove microseconds
            
            if proc.poll() is None:
                status = "RUNNING"
            else:
                status = f"STOPPED (code: {proc.poll()})"
                
            status_lines.append(
                f"{process_name}: {status} | "
                f"PID: {proc_info['pid']} | "
                f"Uptime: {uptime_str} | "
                f"Restarts: {proc_info['restart_count']}"
            )
            
        self.logger.info("\n".join(status_lines))


def create_windows_task_scheduler_xml():
    """Create XML for Windows Task Scheduler to auto-start the monitor."""
    xml_content = '''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Auto-start CatPaw Monitor on system boot</Description>
    <Author>SAP EWM Robot Platform</Author>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>python</Command>
      <Arguments>"D:\EWM Robot\Robotic Platform Codes\monitor_catpaw.py"</Arguments>
      <WorkingDirectory>D:\EWM Robot\Robotic Platform Codes</WorkingDirectory>
    </Exec>
  </Actions>
</Task>'''
    
    xml_path = Path(r"D:\EWM Robot\Robotic Platform Codes") / "catpaw_monitor_task.xml"
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)
        
    print(f"Created Task Scheduler XML at: {xml_path}")
    print("\nTo register the task, run in PowerShell as Administrator:")
    print(f'  schtasks /create /xml "{xml_path}" /tn "CatPawMonitor"')
    

def create_restart_script():
    """Create a simple restart script for manual use."""
    script_content = '''@echo off
echo Stopping CatPaw processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq CatPaw*" 2>nul
timeout /t 5 /nobreak >nul

echo Starting CatPaw Monitor...
cd /d "D:\EWM Robot\Robotic Platform Codes"
python monitor_catpaw.py

pause'''
    
    script_path = Path(r"D:\EWM Robot\Robotic Platform Codes") / "restart_catpaw.bat"
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
        
    print(f"Created restart script at: {script_path}")
    

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CatPaw Process Monitor")
    parser.add_argument("--create-task", action="store_true", 
                       help="Create Windows Task Scheduler XML")
    parser.add_argument("--create-restart-script", action="store_true",
                       help="Create restart script")
    parser.add_argument("--config", default="catpaw_monitor_config.json",
                       help="Path to config file")
    parser.add_argument("--once", action="store_true",
                       help="Run health check once and exit")
    
    args = parser.parse_args()
    
    if args.create_task:
        create_windows_task_scheduler_xml()
    elif args.create_restart_script:
        create_restart_script()
    else:
        monitor = CatPawMonitor(args.config)
        
        if args.once:
            # Run single health check
            print("Running one-time health check...")
            for process_config in monitor.config["processes"]:
                print(f"\nChecking {process_config['name']}:")
                if monitor.config["monitoring"]["enable_process_check"]:
                    is_running = monitor.is_process_running(process_config["name"])
                    print(f"  Process running: {is_running}")
                if monitor.config["monitoring"]["enable_http_check"]:
                    health_url = process_config.get("health_check_url")
                    if health_url:
                        is_healthy = monitor.check_http_health(
                            health_url,
                            process_config["health_check_timeout"]
                        )
                        print(f"  HTTP health check ({health_url}): {is_healthy}")
        else:
            # Run continuous monitoring
            try:
                monitor.run()
            except KeyboardInterrupt:
                print("\nMonitoring stopped by user")