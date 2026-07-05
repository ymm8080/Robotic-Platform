$bytes = [System.IO.File]::ReadAllBytes("D:\EWM Robot\Robotic Platform Codes\scripts\append-today-brief.ps1")
$hex = ($bytes[0..5] | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
Write-Output "First 6 bytes: $hex"
Write-Output "File size: $($bytes.Length) bytes"
