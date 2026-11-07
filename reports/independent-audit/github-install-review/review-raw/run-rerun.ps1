#requires -Version 5.1
# Independent reviewer reruns against Subagent 1's isolated GitHub install venv.
# Writes only under reports/independent-audit/github-install-review/.
$ErrorActionPreference = 'Stop'
$Exe   = 'C:\Users\ACER\AppData\Local\Temp\opencode\weblens-gh-run-20261105\clone\.venv\Scripts\weblens.exe'
$Base  = 'C:\Users\ACER\Downloads\Broswer for ai agnets\reports\independent-audit\github-install-review'
$Raw   = Join-Path $Base 'review-raw'
$Cache = Join-Path $Base 'review-cache'

if (-not (Test-Path $Exe)) { throw "Installed weblens.exe missing: $Exe" }

$CmdDefs = @(
  @{ id = 'rr01-doctor';              args = @('doctor','--pretty') },
  @{ id = 'rr02-search-python314';    args = @('search','Python 3.14 release notes','-k','5','--pretty') },
  @{ id = 'rr03-extract-example-q';   args = @('extract','https://example.com','-q','What is this page?','--max-tokens','300','--pretty') },
  @{ id = 'rr04-extract-example-full';args = @('extract','https://example.com','--full','--max-tokens','300','--pretty') },
  @{ id = 'rr05-extract-example-altq';args = @('extract','https://example.com','-q','documentation examples domain','--max-tokens','300','--pretty') },
  @{ id = 'rr06-research-example';    args = @('research','What is the purpose of example.com?','--max-tokens','500','--pretty') }
)

function Quote-Arg([string]$a) {
  if ($a -match '[\s"]') { return '"' + ($a -replace '"','\"') + '"' }
  return $a
}

$records = @()
foreach ($c in $CmdDefs) {
  $id = $c.id
  $cacheDir = Join-Path $Cache $id
  if (Test-Path $cacheDir) { Remove-Item -Recurse -Force $cacheDir }
  New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

  $outFile = Join-Path $Raw "$id.stdout.txt"
  $errFile = Join-Path $Raw "$id.stderr.txt"
  $metaFile = Join-Path $Raw "$id.meta.json"
  $argLine = (($c.args | ForEach-Object { Quote-Arg $_ }) -join ' ')

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Exe
  $psi.Arguments = $argLine
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
  $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
  $psi.CreateNoWindow = $true
  $psi.WorkingDirectory = $Base
  $psi.EnvironmentVariables['WEBLENS_CACHE_DIR'] = $cacheDir
  $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
  $psi.EnvironmentVariables['PYTHONUTF8'] = '1'

  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  [void]$proc.Start()
  $stdout = $proc.StandardOutput.ReadToEnd()
  $stderr = $proc.StandardError.ReadToEnd()
  $proc.WaitForExit()
  $sw.Stop()

  $utf8 = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($outFile, $stdout, $utf8)
  [System.IO.File]::WriteAllText($errFile, $stderr, $utf8)

  $meta = [ordered]@{
    id              = $id
    exe             = $Exe
    args            = $c.args
    command_line    = "`"$Exe`" $argLine"
    exit_code       = $proc.ExitCode
    wall_seconds    = [math]::Round($sw.Elapsed.TotalSeconds, 3)
    started_at      = (Get-Date).ToString('o')
    cache_dir       = $cacheDir
    cache_preexisting_entries = 0
    stdout_file     = $outFile
    stderr_file     = $errFile
    stdout_bytes    = (Get-Item $outFile).Length
    stderr_bytes    = (Get-Item $errFile).Length
  }
  ($meta | ConvertTo-Json -Depth 8) | Set-Content -Path $metaFile -Encoding UTF8
  $records += [pscustomobject]$meta
  Write-Output ("{0} exit={1} wall={2}s out={3}B err={4}B" -f $id, $proc.ExitCode, $meta.wall_seconds, $meta.stdout_bytes, $meta.stderr_bytes)
}
$records | Format-Table -AutoSize
