param(
    [string]$EventName = ""
)

$TranscriptDir = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\transcripts"
$DateStr = (Get-Date).ToString("yyyy-MM-dd")
$TimeStr = (Get-Date).ToString("HH:mm:ss")
$LogFile = Join-Path $TranscriptDir "transcript-$DateStr.md"

if (-not (Test-Path $TranscriptDir)) {
    New-Item -ItemType Directory -Path $TranscriptDir -Force | Out-Null
}

$HookInput = @{}
try {
    $RawInput = $input | Out-String
    if ($RawInput -and $RawInput.Trim().Length -gt 0) {
        $HookInput = $RawInput | ConvertFrom-Json
    }
} catch {
}

$SessionId = if ($HookInput.session_id) { $HookInput.session_id.Substring(0, 8) } else { "unknown" }
$ToolName = if ($HookInput.tool_name) { $HookInput.tool_name } else { "" }

if ($EventName -eq "SessionStart") {
    if (-not (Test-Path $LogFile)) {
@"
# Claude Code Transcript

> Date: $DateStr
> Project: SAP-EWM Robot Dispatch Platform v3.4
> Path: D:\EWM ROBOT\ROBOTIC PLATFORM CODES\

---

"@ | Out-File -FilePath $LogFile -Encoding UTF8
    }
    $Line = "> [START] Session $TimeStr (ID: $SessionId)`n"
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    exit 0
}

if ($EventName -eq "UserPromptSubmit") {
    $Prompt = ""
    if ($HookInput.tool_input) {
        if ($HookInput.tool_input.GetType().Name -eq "String") {
            $Prompt = $HookInput.tool_input
        } elseif ($HookInput.tool_input.prompt) {
            $Prompt = $HookInput.tool_input.prompt
        } elseif ($HookInput.tool_input.text) {
            $Prompt = $HookInput.tool_input.text
        } else {
            $Prompt = $HookInput.tool_input | ConvertTo-Json -Compress
        }
    }

    if ($Prompt.Length -gt 2000) {
        $Prompt = $Prompt.Substring(0, 2000) + "... [truncated]"
    }

    $Line = @"

## $TimeStr

### User

$Prompt

---
"@
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    exit 0
}

if ($EventName -eq "Stop") {
    $ToolSummary = ""
    if ($HookInput.tool_response -and $HookInput.tool_name) {
        $ToolSummary = " [Used: $($HookInput.tool_name)]"
    }

    $Line = "### Claude ($TimeStr)$ToolSummary`n`n"
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    exit 0
}

if ($EventName -eq "PostToolUse") {
    if ($ToolName -eq "Write" -or $ToolName -eq "Edit") {
        $FilePath = ""
        if ($HookInput.tool_input -and $HookInput.tool_input.file_path) {
            $FilePath = $HookInput.tool_input.file_path
        }
        $RelPath = ""
        $BasePath = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\"
        if ($FilePath.StartsWith($BasePath)) {
            $RelPath = $FilePath.Substring($BasePath.Length)
        } else {
            $RelPath = $FilePath
        }
        $ActionTag = if ($ToolName -eq "Write") { "CREATE" } else { "MODIFY" }
        $Line = "  - [$ActionTag] FILE: $RelPath  "
        Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    }
    exit 0
}
