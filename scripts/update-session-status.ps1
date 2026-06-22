param()

$TranscriptDir = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\transcripts"
$StatusFile = "D:\EWM ROBOT\ROBOTIC PLATFORM CODES\SESSION_STATUS.md"
$DateStr = (Get-Date).ToString("yyyy-MM-dd")
$TimeStr = (Get-Date).ToString("HH:mm:ss")
$TodayFile = Join-Path $TranscriptDir "transcript-$DateStr.md"

# Parse transcript
$UserMessages = @()
$FileChanges = @()
$TurnCount = 0

if (Test-Path $TodayFile) {
    $Lines = Get-Content $TodayFile -Encoding UTF8
    $CurrentSection = ""
    $CurrentUserText = ""

    foreach ($Line in $Lines) {
        if ($Line -match "^## ") {
            if ($CurrentUserText.Trim() -ne "") {
                $UserMessages += @{ Text = $CurrentUserText.Trim() }
            }
            $CurrentUserText = ""
        }
        elseif ($Line -match "^### User$") {
            $CurrentSection = "user"
        }
        elseif ($Line -match "^### Claude") {
            $CurrentSection = "claude"
            if ($CurrentUserText.Trim() -ne "") {
                $UserMessages += @{ Text = $CurrentUserText.Trim() }
            }
            $CurrentUserText = ""
            $TurnCount++
        }
        elseif ($Line -match "\[(CREATE|MODIFY)\] FILE: (.+)") {
            $Action = $Matches[1]
            $FilePath = $Matches[2].Trim()
            if ($FilePath -notin ($FileChanges | ForEach-Object { $_.Path })) {
                $FileChanges += @{ Path = $FilePath; Action = $Action }
            }
        }
        elseif ($CurrentSection -eq "user" -and $Line -notmatch "^---$" -and $Line.Trim() -ne "") {
            $CurrentUserText += $Line.Trim() + " "
        }
    }

    if ($CurrentUserText.Trim() -ne "") {
        $UserMessages += @{ Text = $CurrentUserText.Trim() }
    }
}

# Build section strings
$completedLines = @()
if ($UserMessages.Count -gt 0) {
    $count = 0
    foreach ($Msg in $UserMessages) {
        $Short = $Msg.Text
        if ($Short.Length -gt 120) { $Short = $Short.Substring(0, 120) + "..." }
        $completedLines += "- $Short"
        $count++
        if ($count -ge 15) {
            $remaining = $UserMessages.Count - 15
            if ($remaining -gt 0) { $completedLines += "- (+ $remaining more)" }
            break
        }
    }
} else {
    $completedLines += "- (Session started, no user messages recorded)"
}
$completedSection = $completedLines -join "`n"

$fileChangeLines = @()
if ($FileChanges.Count -gt 0) {
    foreach ($Fc in $FileChanges) {
        $fileChangeLines += "- [$($Fc.Action)] $($Fc.Path)"
    }
} else {
    $fileChangeLines += "- (none)"
}
$fileChangeSection = $fileChangeLines -join "`n"

# Build and write status file
$NewStatus = "# Project Session Status" + "`n"
$NewStatus += "> Auto-generated. Updated at session end on $DateStr $TimeStr." + "`n"
$NewStatus += "`n"
$NewStatus += "## Current Phase" + "`n"
$NewStatus += "Phase 3: Production Readiness (Week 7-8)" + "`n"
$NewStatus += "`n"
$NewStatus += "## Last Session ($DateStr)" + "`n"
$NewStatus += "`n"
$NewStatus += "### Completed This Session" + "`n"
$NewStatus += $completedSection + "`n"
$NewStatus += "`n"
$NewStatus += "### File Changes ($($FileChanges.Count) files)" + "`n"
$NewStatus += $fileChangeSection + "`n"
$NewStatus += "`n"
$NewStatus += "### Key Decisions" + "`n"
$NewStatus += "- (See transcript for full details: transcripts/transcript-$DateStr.md)" + "`n"
$NewStatus += "`n"
$NewStatus += "### Next Steps (Priority Order)" + "`n"
$NewStatus += "1. Review this session's output for completion" + "`n"
$NewStatus += "2. Continue from Phase 3 execution plan" + "`n"
$NewStatus += "`n"
$NewStatus += "---" + "`n"
$NewStatus += "> Last updated: $DateStr $TimeStr" + "`n"

$NewStatus | Out-File -FilePath $StatusFile -Encoding utf8 -Force
