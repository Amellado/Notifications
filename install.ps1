<#
.SYNOPSIS
    One-shot installer for attention_notify on Windows.

.DESCRIPTION
    Finds a usable Python 3.8+ interpreter, checks ffmpeg (only needed for .mp3
    sounds), writes config.json for this machine, and registers the notification
    hook globally for Claude Code and Codex.

    Safe to re-run: it rewrites config.json and replaces the existing hook entry
    rather than stacking duplicates.

.PARAMETER Python
    Path to a specific python.exe. Skips autodetection.

.PARAMETER Sounds
    Folder holding your sound files. Defaults to <repo>\sounds.

.PARAMETER SkipTest
    Do not play a test sound at the end.

.EXAMPLE
    .\install.ps1

.EXAMPLE
    .\install.ps1 -Sounds "D:\my-sounds" -SkipTest
#>
[CmdletBinding()]
param(
    [string]$Python,
    [string]$Sounds,
    [switch]$SkipTest
)

$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$runner = Join-Path $repoRoot 'attention_notify.py'

function Write-Step { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    OK  $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "    !   $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "    X   $Message" -ForegroundColor Red }

# Native exe stderr trips NativeCommandError under ErrorActionPreference=Stop
# on PowerShell 5.1, so every runner call goes through here.
function Invoke-Runner {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $script:pythonPath $runner @Arguments 2>&1 | ForEach-Object { Write-Host "    $_" }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

if (-not (Test-Path -LiteralPath $runner)) {
    Write-Fail 'attention_notify.py not found next to this script. Run install.ps1 from inside the cloned repo.'
    exit 1
}

# --- Python -----------------------------------------------------------------
# A candidate is only accepted if it actually runs, reports 3.8+, and can import
# winsound. That rules out the Microsoft Store stub and non-Windows builds.
function Resolve-Python {
    param([string]$Exe, [string[]]$PreArgs = @())

    $probe = 'import sys, winsound; print(sys.executable); print("%d.%d" % sys.version_info[:2]); print(sys.version_info >= (3, 8))'

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Exe @PreArgs '-c' $probe 2>$null
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }

    $lines = @($output) | Where-Object { "$_".Trim() -ne '' }
    if ($lines.Count -lt 3 -or "$($lines[2])".Trim() -ne 'True') { return $null }

    $resolved = "$($lines[0])".Trim()
    if (-not (Test-Path -LiteralPath $resolved)) { return $null }

    return [pscustomobject]@{ Path = $resolved; Version = "$($lines[1])".Trim() }
}

Write-Step 'Looking for Python 3.8+'
# Note: $interpreter, not $python — PowerShell variable names are case
# insensitive, so $python would collide with the [string]$Python parameter and
# silently stringify the result object.
$interpreter = $null

if ($Python) {
    if (-not (Test-Path -LiteralPath $Python)) {
        Write-Fail "-Python path does not exist: $Python"
        exit 1
    }
    $interpreter = Resolve-Python -Exe $Python
    if (-not $interpreter) {
        Write-Fail "$Python is not a usable Python 3.8+ with winsound support."
        exit 1
    }
} else {
    $candidates = New-Object System.Collections.ArrayList

    # py launcher first — it is the most reliable entry point on Windows.
    [void]$candidates.Add(@{ Exe = 'py'; PreArgs = @('-3') })

    # Then PATH, skipping the zero-byte Microsoft Store stubs that pop the Store.
    foreach ($name in @('python', 'python3')) {
        $commands = @(Get-Command $name -CommandType Application -ErrorAction SilentlyContinue)
        foreach ($command in $commands) {
            $source = $command.Source
            if ($source -like '*\WindowsApps\*') {
                $item = Get-Item -LiteralPath $source -ErrorAction SilentlyContinue
                if (-not $item -or $item.Length -eq 0) { continue }
            }
            [void]$candidates.Add(@{ Exe = $source; PreArgs = @() })
        }
    }

    # Finally common install locations and uv-managed interpreters.
    $globs = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe'),
        (Join-Path $env:ProgramFiles 'Python3*\python.exe'),
        'C:\Python3*\python.exe',
        (Join-Path $env:APPDATA 'uv\python\cpython-*\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'uv\python\cpython-*\python.exe')
    )
    foreach ($glob in $globs) {
        if (-not $glob) { continue }
        # Newest first, so we do not settle on an ancient 3.8.
        $found = @(Get-ChildItem -Path $glob -ErrorAction SilentlyContinue |
                   Sort-Object -Property FullName -Descending)
        foreach ($entry in $found) {
            [void]$candidates.Add(@{ Exe = $entry.FullName; PreArgs = @() })
        }
    }

    foreach ($candidate in $candidates) {
        $interpreter = Resolve-Python -Exe $candidate.Exe -PreArgs $candidate.PreArgs
        if ($interpreter) { break }
    }
}

if (-not $interpreter) {
    Write-Fail 'No usable Python 3.8+ found.'
    Write-Host ''
    Write-Host '    Install it with one of these, then re-run .\install.ps1:'
    Write-Host '      winget install Python.Python.3.13'
    Write-Host '      https://www.python.org/downloads/windows/  (tick "Add python.exe to PATH")'
    Write-Host ''
    Write-Host '    Already have Python somewhere unusual? Point at it directly:'
    Write-Host '      .\install.ps1 -Python "C:\path\to\python.exe"'
    exit 1
}
$script:pythonPath = $interpreter.Path
Write-Ok "Python $($interpreter.Version) at $($interpreter.Path)"

# --- Sounds -----------------------------------------------------------------
Write-Step 'Checking sounds folder'
$configPath = Join-Path $repoRoot 'config.json'

if (-not $Sounds) {
    # Reuse sound_dir from a previous install if it still points somewhere real.
    if (Test-Path -LiteralPath $configPath) {
        try {
            $existing = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            if ($existing.sound_dir -and (Test-Path -LiteralPath $existing.sound_dir)) {
                $Sounds = $existing.sound_dir
            }
        } catch {
            Write-Warn 'Existing config.json is unreadable; it will be regenerated.'
        }
    }
}
if (-not $Sounds) { $Sounds = Join-Path $repoRoot 'sounds' }

if (-not (Test-Path -LiteralPath $Sounds)) {
    New-Item -ItemType Directory -Path $Sounds -Force | Out-Null
    Write-Warn "Created $Sounds"
}
$soundsFull = (Resolve-Path -LiteralPath $Sounds).Path

$mp3 = @(Get-ChildItem -LiteralPath $soundsFull -Filter '*.mp3' -Recurse -File -ErrorAction SilentlyContinue)
$wav = @(Get-ChildItem -LiteralPath $soundsFull -Filter '*.wav' -Recurse -File -ErrorAction SilentlyContinue)
$soundCount = $mp3.Count + $wav.Count

if ($soundCount -eq 0) {
    Write-Warn "No sounds in $soundsFull"
    Write-Host '        The hook installs fine but stays silent until you add audio.'
    Write-Host '        Drop short .mp3 or .wav clips in there (.wav needs no ffmpeg).'
} else {
    Write-Ok "$soundCount sound file(s) found ($($mp3.Count) mp3, $($wav.Count) wav)"
}

# --- ffmpeg (mp3 only) ------------------------------------------------------
Write-Step 'Checking ffmpeg (only needed for .mp3 sounds)'
$ffmpeg = 'ffmpeg'
$ffmpegFound = $null

$onPath = Get-Command 'ffmpeg' -CommandType Application -ErrorAction SilentlyContinue |
          Select-Object -First 1
if ($onPath) {
    $ffmpegFound = $onPath.Source
} else {
    $wingetGlob = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin\ffmpeg.exe'
    $wingetMatch = Get-ChildItem -Path $wingetGlob -ErrorAction SilentlyContinue |
                   Sort-Object -Property FullName -Descending |
                   Select-Object -First 1
    if ($wingetMatch) { $ffmpegFound = $wingetMatch.FullName }
}

if ($ffmpegFound) {
    $ffmpeg = $ffmpegFound
    Write-Ok "ffmpeg at $ffmpegFound"
} elseif ($mp3.Count -gt 0) {
    Write-Warn 'ffmpeg not found, but you have .mp3 sounds — they cannot be played without it.'
    Write-Host '        Fix with:  winget install Gyan.FFmpeg     (then re-run .\install.ps1)'
    Write-Host '        Or use .wav sounds instead, which play with no extra tooling.'
} else {
    Write-Ok 'not needed (no .mp3 sounds)'
}

# --- config.json ------------------------------------------------------------
Write-Step 'Writing config.json'
$config = [ordered]@{
    notifications_root = ($repoRoot         -replace '\\', '/')
    sound_dir          = ($soundsFull       -replace '\\', '/')
    python_executable  = ($interpreter.Path -replace '\\', '/')
    ffmpeg_executable  = ($ffmpeg           -replace '\\', '/')
}
($config | ConvertTo-Json) | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Ok $configPath

# --- Register the hook ------------------------------------------------------
Write-Step 'Registering the global hook (Claude Code + Codex)'
if ((Invoke-Runner 'setup-global' '--sounds' $soundsFull) -ne 0) {
    Write-Fail 'setup-global failed.'
    exit 1
}
Write-Ok 'hook registered'

# --- Precache + test --------------------------------------------------------
if ($mp3.Count -gt 0 -and $ffmpegFound) {
    Write-Step 'Precaching mp3 to wav (keeps the first playback instant)'
    [void](Invoke-Runner 'precache' '--sounds' $soundsFull)
}

if (-not $SkipTest -and $soundCount -gt 0) {
    Write-Step 'Playing a test sound'
    if ((Invoke-Runner 'worker' '--sounds' $soundsFull '--debug') -ne 0) {
        Write-Warn 'Test playback did not succeed — see the messages above.'
    }
}

Write-Host ''
Write-Host 'Done. Restart Claude Code so it picks up the new hook.' -ForegroundColor Green
