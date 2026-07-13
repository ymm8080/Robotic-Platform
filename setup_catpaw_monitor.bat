@echo off
echo ==============================================
echo CatPaw Monitor Setup Script
echo ==============================================

echo.
echo Step 1: Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and add it to PATH
    pause
    exit /b 1
)
echo ✓ Python is installed

echo.
echo Step 2: Installing required packages...
pip install psutil requests >nul 2>&1
if errorlevel 1 (
    echo WARNING: Failed to install packages via pip, trying pip3...
    pip3 install psutil requests >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Failed to install required packages
        echo Please install manually: pip install psutil requests
        pause
        exit /b 1
    )
)
echo ✓ Required packages installed

echo.
echo Step 3: Creating Windows Task Scheduler job...
echo This will create a task that starts the monitor on system startup
echo.
echo IMPORTANT: This step requires Administrator privileges
echo.

set /p createTask="Create Windows Task Scheduler job? (Y/N): "
if /i "%createTask%"=="Y" (
    echo Creating Task Scheduler XML...
    python monitor_catpaw.py --create-task
    
    echo.
    echo To register the task, open PowerShell as Administrator and run:
    echo   schtasks /create /xml "catpaw_monitor_task.xml" /tn "CatPawMonitor"
    echo.
    echo Or manually import the XML file in Task Scheduler
)

echo.
echo Step 4: Creating restart script...
python monitor_catpaw.py --create-restart-script
echo ✓ Created restart_catpaw.bat

echo.
echo Step 5: Creating startup shortcut...
echo Creating startup shortcut in Start Menu...

rem Create shortcut in startup folder
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
if exist "%STARTUP%" (
    echo [InternetShortcut] > "%STARTUP%\CatPaw Monitor.url"
    echo URL=file:///D:/EWM%20Robot/Robotic%20Platform%20Codes/monitor_catpaw.py >> "%STARTUP%\CatPaw Monitor.url"
    echo IconIndex=0 >> "%STARTUP%\CatPaw Monitor.url"
    echo IconFile=C:\Windows\System32\SHELL32.dll >> "%STARTUP%\CatPaw Monitor.url"
    echo ✓ Created startup shortcut
) else (
    echo WARNING: Could not find startup folder
)

echo.
echo Step 6: Testing monitor...
echo Running one-time health check...
python monitor_catpaw.py --once --config catpaw_monitor_config.json

echo.
echo ==============================================
echo SETUP COMPLETE
echo ==============================================
echo.
echo Available commands:
echo   1. Start monitor manually: python monitor_catpaw.py
echo   2. Restart all CatPaw services: restart_catpaw.bat
echo   3. Check health status: python monitor_catpaw.py --once
echo.
echo Configuration files:
echo   - catpaw_monitor_config.json (edit to add/remove processes)
echo   - catpaw_monitor.log (monitor logs)
echo   - catpaw_alerts.log (alert logs)
echo.
echo Next steps:
echo   1. Edit catpaw_monitor_config.json to match your setup
echo   2. Register the Windows Task Scheduler job (as Administrator)
echo   3. Start the monitor: python monitor_catpaw.py
echo.
pause