# Actual Windows Task Scheduler acceptance: two OS-triggered distinct
# host_tick processes and independent authoritative SQLite/immutable readback.
# Runs only inside a temporary GitHub hosted Windows runner in CI.
[CmdletBinding()]
param([ValidateRange(70,240)][int]$TimeoutSeconds=180)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python=(Get-Command python.exe -ErrorAction Stop).Source
$probe=(Join-Path $PSScriptRoot 'verify_windows_scheduler_probe.py')
$register=(Join-Path $PSScriptRoot 'register_windows_host.ps1')
$root=Join-Path $env:RUNNER_TEMP ('cognition-schedule-'+[guid]::NewGuid().ToString('N'))
$taskName=('CognitionOS-CI-'+[guid]::NewGuid().ToString('N'))
$created=$false
try {
    $seedText=& $python $probe seed --root $root
    if ($LASTEXITCODE -ne 0) { throw "Unable to seed isolated probe: $seedText" }
    $seed=$seedText | ConvertFrom-Json
    if ($seed.status -ne 'SEEDED_BY_TEST_PROCESS') { throw 'Seed report invalid' }
    $first=(Get-Date).AddSeconds(40)
    $invalid=Join-Path $root 'empty.sqlite'
    [System.IO.File]::WriteAllBytes($invalid,[byte[]]@())
    $badName=$taskName+'-invalid'
    $rejected=$false
    try {
        & $register -TaskName $badName -PythonPath $python -DbPath $invalid -WorkspacePath $seed.workspace -FixturesPath $seed.fixtures -FirstRunAt $first -IntervalMinutes 1 -DurationDays 1 | Out-Null
    }
    catch {
        $rejected=$true
    }
    if (-not $rejected -or (Get-ScheduledTask -TaskName $badName -ErrorAction SilentlyContinue)) {
        throw 'An uninitialized SQLite authority was allowed to create a Windows Scheduled Task'
    }
    Write-Output 'UNSEEDED_AUTHORITY_REGISTRATION: BLOCKED'
    $registered=& $register -TaskName $taskName -PythonPath $python -DbPath $seed.db -WorkspacePath $seed.workspace -FixturesPath $seed.fixtures -FirstRunAt $first -IntervalMinutes 1 -DurationDays 1
    if (-not (Get-ScheduledTask -TaskName $taskName -ErrorAction Stop)) {
        throw 'Task Scheduler did not retain the registered native task'
    }
    $created=$true
    $registration=$registered | ConvertFrom-Json
    if ($registration.status -ne 'REGISTERED_USER_INTERACTIVE' -or $registration.auto_stage_goals) {
        throw 'Native task registration did not retain a safe scope'
    }
    Write-Output ('REGISTERED: '+$registered)
    $end=(Get-Date).AddSeconds($TimeoutSeconds)
    $latest=$null
    $verified=$false
    do {
        Start-Sleep -Seconds 5
        $result=& $python $probe audit --root $root
        $latest=$result | ConvertFrom-Json
        if ($latest.status -eq 'HOSTED_WINDOWS_SCHEDULER_WITNESSED') {
            $info=Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction Stop
            if ($info.LastTaskResult -ne 0) {
                throw ("Task ran with nonzero native Scheduler result: "+$info.LastTaskResult)
            }
            # Evidence is the DB+artifacts; Scheduler LastTaskResult alone
            # cannot establish that tasks were actually processed.
            Write-Output ('OS_SCHEDULER_EVIDENCE: '+$result)
            Write-Output ('TASK_LAST_RUN_TIME: '+$info.LastRunTime.ToString('o'))
            $verified=$true
            break
        }
    } while ((Get-Date) -lt $end)
    if (-not $verified) {
        throw ("Native scheduler proof timed out: "+($latest | ConvertTo-Json -Compress))
    }
}
finally {
    if ($created) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            throw 'Failed to remove temporary scheduler task'
        }
        Write-Output 'TEMPORARY_SCHEDULER_TASK_REMOVED'
    }
    # Prefer cleanup of isolated test artifacts; do not delete originals.
    if ((Test-Path -LiteralPath $root) -and
        $root.StartsWith($env:RUNNER_TEMP,[System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
    }
}
