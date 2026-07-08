param([string]$Path)
$bytes = [System.IO.File]::ReadAllBytes($Path)
$bom = [byte[]](0xEF, 0xBB, 0xBF)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    Write-Output "BOM already present in $Path"
    exit 0
}
$newBytes = New-Object byte[] ($bom.Length + $bytes.Length)
[Array]::Copy($bom, 0, $newBytes, 0, $bom.Length)
[Array]::Copy($bytes, 0, $newBytes, $bom.Length, $bytes.Length)
[System.IO.File]::WriteAllBytes($Path, $newBytes)
Write-Output "BOM added to $Path"
