# Run this script as Administrator (right-click PowerShell -> Run as administrator)
# Finishes RabbitMQ setup: Erlang 27 + service start + management UI

$ErrorActionPreference = 'Stop'
$ErlangInstaller = "$env:TEMP\otp_win64_27.3.4.7.exe"
$ErlangHome = 'C:\Program Files\Erlang OTP'
$RabbitSbin = 'C:\Program Files\RabbitMQ Server\rabbitmq_server-4.3.1\sbin'
$RabbitData = "$env:APPDATA\RabbitMQ\db"

if (-not (Test-Path $ErlangInstaller)) {
    Write-Host "Downloading Erlang 27.3.4.7..."
    $url = 'https://erlang.org/download/otp_win64_27.3.4.7.exe'
    Invoke-WebRequest -Uri $url -OutFile $ErlangInstaller -UseBasicParsing
}

if (-not (Test-Path "$ErlangHome\bin\erl.exe")) {
    Write-Host "Installing Erlang 27.3.4.7..."
    $p = Start-Process -FilePath $ErlangInstaller -ArgumentList '/S' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Erlang installer failed with exit code $($p.ExitCode)" }
}

[Environment]::SetEnvironmentVariable('ERLANG_HOME', $ErlangHome, 'Machine')
$env:ERLANG_HOME = $ErlangHome

# Fresh data dir after failed Erlang 29 boot (safe for new installs)
if (Test-Path $RabbitData) {
    Write-Host "Resetting RabbitMQ data directory..."
    Stop-Service RabbitMQ -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $RabbitData
}

Write-Host "Reinstalling RabbitMQ Windows service..."
& "$RabbitSbin\rabbitmq-service.bat" stop 2>$null
& "$RabbitSbin\rabbitmq-service.bat" remove 2>$null
& "$RabbitSbin\rabbitmq-service.bat" install
& "$RabbitSbin\rabbitmq-service.bat" start

Start-Sleep -Seconds 8
& "$RabbitSbin\rabbitmq-plugins.bat" enable rabbitmq_management
& "$RabbitSbin\rabbitmq-service.bat" stop
& "$RabbitSbin\rabbitmq-service.bat" start

Start-Sleep -Seconds 5
& "$RabbitSbin\rabbitmqctl.bat" status

Write-Host ""
Write-Host "RabbitMQ is ready."
Write-Host "  AMQP:      amqp://guest:guest@localhost:5672/"
Write-Host "  Management UI: http://localhost:15672/  (guest / guest)"
Write-Host "  Service:   Get-Service RabbitMQ"
