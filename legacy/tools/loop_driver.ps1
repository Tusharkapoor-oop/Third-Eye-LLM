# tools/loop_driver.ps1
# Continuous execution driver for WebLens Autonomous Quality Loop (v8 Part A2)

param (
    [int]$MaxRestartsPerHour = 10,
    [int]$InitialBackoffSec = 5,
    [int]$MaxBackoffSec = 60,
    [string]$LogFile = "evidence/loop/driver.log"
)

$ErrorActionPreference = "Continue"
$StateFile = "evidence/loop/STATE.json"
$StopFile = "STOP"
$PauseFile = "PAUSE"
$DoneFile = "evidence/loop/DONE"

Function Log-Message([string]$msg) {
    $timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    $entry = "[$timestamp] $msg"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry
}

Log-Message "WebLens Loop Driver started (PowerShell)."

$restartsThisHour = 0
$hourStart = (Get-Date)
$currentBackoff = $InitialBackoffSec

while ($true) {
    # Check STOP file
    if (Test-Path $StopFile) {
        Log-Message "STOP file detected. Ending loop gracefully."
        break
    }

    # Check DONE file
    if (Test-Path $DoneFile) {
        Log-Message "DONE file detected. All stop rules achieved."
        break
    }

    # Check PAUSE file
    if (Test-Path $PauseFile) {
        Log-Message "PAUSE file detected. Waiting 10 seconds..."
        Start-Sleep -Seconds 10
        continue
    }

    # Verify hourly restart limit
    $now = (Get-Date)
    if (($now - $hourStart).TotalHours -ge 1.0) {
        $restartsThisHour = 0
        $hourStart = $now
    }

    if ($restartsThisHour -ge $MaxRestartsPerHour) {
        Log-Message "WARNING: Exceeded $MaxRestartsPerHour restarts this hour. Backing off 300 seconds."
        Start-Sleep -Seconds 300
        continue
    }

    Log-Message "Starting cycle step. Reading $StateFile..."
    if (-not (Test-Path $StateFile)) {
        Log-Message "ERROR: State file $StateFile does not exist. Halting driver."
        break
    }

    # Launch cycle step via Python verification and test run
    $t0 = Get-Date
    & .\.venv\Scripts\python.exe -m pytest tests/test_01_static_and_deps.py tests/test_02_mcp_protocol.py tests/test_03_security_boundaries.py tests/test_04_fuzz_and_chaos.py tests/test_05_extraction_quality.py tests/test_06_performance_stress.py -q
    $exitCode = $LASTEXITCODE

    $duration = ((Get-Date) - $t0).TotalSeconds
    if ($exitCode -eq 0) {
        Log-Message "Cycle execution succeeded in ${duration}s."
        $currentBackoff = $InitialBackoffSec
    } else {
        $restartsThisHour++
        Log-Message "Cycle step exited with code $exitCode in ${duration}s. Backing off ${currentBackoff}s."
        Start-Sleep -Seconds $currentBackoff
        $currentBackoff = [Math]::Min($currentBackoff * 2, $MaxBackoffSec)
    }

    Start-Sleep -Seconds 2
}

Log-Message "WebLens Loop Driver terminated."

