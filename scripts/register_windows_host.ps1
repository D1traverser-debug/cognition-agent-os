# Explicit, least-privilege opt-in only. No remote downloads, auto grant,
# model requests, credentials or automatic registration during install.
# The task runs only while the selected current Windows user is logged on.
[CmdletBinding()]
param(
    [ValidateRange(1,1440)][int]$IntervalMinutes = 5,
    [ValidatePattern('^[a-zA-Z0-9_.-]{3,90}$')][string]$TaskName = 'CognitionAgentOS-Local',
    [switch]$AutoStageGoals,
    [string]$DbPath,
    [string]$WorkspacePath,
    [string]$FixturesPath,
    [string]$PythonPath,
    [datetime]$FirstRunAt = [datetime]::MinValue,
    [ValidateRange(1,365)][int]$DurationDays = 30
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $PythonPath) { $PythonPath=(Get-Command python.exe -ErrorAction Stop).Source }
if (-not $DbPath) { $DbPath=Join-Path $root 'runtime\state.sqlite' }
if (-not $WorkspacePath) { $WorkspacePath=Join-Path $root 'runtime\workspace' }
if (-not $FixturesPath) { $FixturesPath=Join-Path $root 'fixtures' }
if ($FirstRunAt -eq [datetime]::MinValue) { $FirstRunAt=(Get-Date).AddMinutes(2) }
if ($FirstRunAt -le (Get-Date).AddSeconds(10)) {
    throw 'FirstRunAt must be in the future'
}
function Require-File([string]$PathValue,[string]$Purpose) {
    $item=Get-Item -LiteralPath $PathValue -ErrorAction Stop
    if ($item.PSIsContainer -or $item.LinkType) {
        throw "$Purpose must be an existing non-link regular file"
    }
    return $item.FullName
}
$python=Require-File $PythonPath 'Python interpreter'
$runner=Require-File (Join-Path $root 'scripts\host_tick.py') 'Host entrypoint'
$db=Require-File $DbPath 'Preseeded SQLite authority'
$fixtures=(Resolve-Path -LiteralPath $FixturesPath -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $fixtures -PathType Container)) {
    throw 'Fixtures must be an existing directory'
}
if (-not [System.IO.Path]::IsPathRooted($WorkspacePath)) {
    throw 'Workspace path must be absolute'
}
$workspace=[System.IO.Path]::GetFullPath($WorkspacePath)
if ((Test-Path -LiteralPath $workspace) -and
    -not (Test-Path -LiteralPath $workspace -PathType Container)) {
    throw 'Workspace path must be a directory'
}
if (-not (Test-Path -LiteralPath $workspace)) {
    New-Item -ItemType Directory -Path $workspace -Force | Out-Null
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Task already exists: refusing to overwrite: $TaskName"
}
$arguments=('"{0}" --db "{1}" --workspace "{2}" --fixtures "{3}" host-tick --max-jobs 16' -f $runner,$db,$workspace,$fixtures)
if ($AutoStageGoals) { $arguments+=' --auto-stage-goals' }
$action=New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $root
$trigger=New-ScheduledTaskTrigger -Once -At $FirstRunAt -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days $DurationDays)
$principal=New-ScheduledTaskPrincipal -UserId ("{0}\{1}" -f $env:USERDOMAIN,$env:USERNAME) -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Opt-in local evidence tick, user-interactive, bounded' -ErrorAction Stop | Out-Null
[pscustomobject]@{
  status='REGISTERED_USER_INTERACTIVE'
  task_name=$TaskName
  first_run=$FirstRunAt.ToString('o')
  interval_minutes=$IntervalMinutes
  duration_days=$DurationDays
  auto_stage_goals=[bool]$AutoStageGoals
  preseeded_authority=$db
  note='Only when current user is logged on; NOT proof of execution before login or after reboot.'
} | ConvertTo-Json -Compress
