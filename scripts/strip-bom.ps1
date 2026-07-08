$f = $args[0]
$c = Get-Content $f -Raw -Encoding UTF8
if ($c.Length -gt 0 -and $c[0] -eq [char]0xFEFF) {
    $c = $c.Substring(1)
    [System.IO.File]::WriteAllText($f, $c, [System.Text.UTF8Encoding]::new($false))
    Write-Output "BOM stripped from $f"
} else {
    Write-Output "No BOM found in $f"
}
