param()

$TranscriptDir = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\transcripts"
$StatusFile = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\SESSION_STATUS.md"
$DateStr = (Get-Date).ToString("yyyy-MM-dd")
$Yesterday = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
$LogFile = Join-Path $TranscriptDir "transcript-$DateStr.md"
$YesterdayFile = Join-Path $TranscriptDir "transcript-$Yesterday.md"

$ContextParts = @()

if (Test-Path $StatusFile) {
    $StatusContent = Get-Content $StatusFile -Encoding UTF8 -Raw

    $Phase = ""
    $LastSession = ""
    $NextSteps = ""

    if ($StatusContent -match "(?ms)Current Phase\s*\n(.+?)(?=\n##)") {
        $Phase = $Matches[1].Trim()
    }
    if ($StatusContent -match "(?ms)Last Session.*?\n(.+?)(?=\n## )") {
        $LastSession = $Matches[1].Trim()
    }
    if ($StatusContent -match "(?ms)Next Steps.*?\n(.+?)(?=\n##)") {
        $NextSteps = $Matches[1].Trim()
    }

    $StatusSummary = @"

** Project Status Overview **
> File: SESSION_STATUS.md

** Current Phase: ** $Phase

$(if ($LastSession) { "** Last Session Summary: **`n$LastSession`n" } else { "" })
$(if ($NextSteps) { "** Next Steps: **`n$NextSteps`n" } else { "" })
"@
    $ContextParts += $StatusSummary
}

$SourceFile = $LogFile
if (-not (Test-Path $SourceFile)) {
    $SourceFile = $YesterdayFile
}

if (Test-Path $SourceFile) {
    $Content = Get-Content $SourceFile -Encoding UTF8 -Raw
    $Sections = $Content -split "(?=^## \d{2}:)"
    $TurnsToShow = [Math]::Min(4, ($Sections.Count - 1))

    if ($TurnsToShow -gt 0) {
        $RecentTurns = $Sections[-$TurnsToShow..-1] -join "`n"
        $TranscriptSummary = @"
** Recent Transcript (last $TurnsToShow turns): **
$RecentTurns
---
"@
        $ContextParts += $TranscriptSummary
    }
}

$Instructions = @"
** Instructions: **
1. After reading the project status above, you have the full context.
2. SESSION_STATUS.md is the memory anchor - it records phase, completed items, next steps.
3. If user asks 'where are we', reference SESSION_STATUS.md.
"@
$ContextParts += $Instructions

$AdditionalContext = $ContextParts -join "`n`n"

if ($AdditionalContext.Length -gt 8000) {
    $AdditionalContext = $AdditionalContext.Substring(0, 8000) + "`n`n[truncated]"
}

$Output = @{
    hookSpecificOutput = @{
        hookEventName = "SessionStart"
        additionalContext = $AdditionalContext
    }
}

$Output | ConvertTo-Json -Compress
