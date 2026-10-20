# Explicit opt-in by the owner. No admin rights, cloud LLM, or tokens are requested.
# Run from PowerShell: powershell -ExecutionPolicy Bypass -File .\scripts\register_windows_host.ps1
param(
    [ValidateRange(1, 1440)][int]$IntervalMinutes = 5,
    [string]$TaskName = "CognitionAgentOS-Local"
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = (Get-Command python.exe -ErrorAction Stop).Source
$runner = Join-Path $root 'scripts\host_tick.py'
$db = Join-Path $root 'runtime\state.sqlite'
$workspace = Join-Path $root 'runtime\workspace'
$fixtures = Join-Path $root 'fixtures'
if (-not (Test-Path -LiteralPath $db -PathType Leaf)) {
    throw "Seed an explicit task first; host will not bootstrap its own write grant: $db"
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Task already exists; refusing to overwrite: $TaskName"
}
$arguments = ('"{0}" --db "{1}" --workspace "{2}" --fixtures "{3}" host-tick --max-jobs 16' -f $runner, $db, $workspace, $fixtures)
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Local cognition evidence tick (no cloud model API)' | Out-Null
Write-Output "Registered $TaskName. Verify with: Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Output "To disable: Disable-ScheduledTask -TaskName '$TaskName'; to remove: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
