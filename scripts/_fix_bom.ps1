$path = "D:\EWM Robot\Robotic Platform Codes\scripts\append-today-brief.ps1"
$bytes = [System.IO.File]::ReadAllBytes($path)
# Check for double BOM (EF BB BF EF BB BF)
if ($bytes.Length -ge 6 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF -and $bytes[3] -eq 0xEF -and $bytes[4] -eq 0xBB -and $bytes[5] -eq 0xBF) {
    Write-Output "Double BOM detected, fixing..."
    # Keep only one BOM (first 3 bytes) + rest of file (skip first 6, take from 3)
    $fixed = New-Object byte[] ($bytes.Length - 3)
    [Array]::Copy($bytes, 0, $fixed, 0, 3)   # First BOM
    [Array]::Copy($bytes, 6, $fixed, 3, $bytes.Length - 6)  # Rest after double BOM
    [System.IO.File]::WriteAllBytes($path, $fixed)
    Write-Output "Fixed. New size: $($fixed.Length) bytes"
    # Verify
    $check = [System.IO.File]::ReadAllBytes($path)
    $hex = ($check[0..5] | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
    Write-Output "First 6 bytes after fix: $hex"
} else {
    Write-Output "No double BOM found. First bytes: $(($bytes[0..5] | ForEach-Object { '{0:X2}' -f $_ }) -join ' ')"
}
