# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Cadence Studio contributors
# Run in a dedicated pwsh controller process; its descendants inherit the Job.
#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Executable,
    [Parameter(Mandatory)][string]$ExpectedExecutableSha256,
    [Parameter(Mandatory)][string]$EngineExecutable,
    [Parameter(Mandatory)][string]$CtestLog,
    [Parameter(Mandatory)][string]$BuildState,
    [Parameter(Mandatory)][string]$BuildResult,
    [Parameter(Mandatory)][string]$EngineBuildReceipt,
    [Parameter(Mandatory)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Use disposable native Windows x64 hosted CI.'
}
$qaRoot = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\','/')
$tempRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')
if (-not $qaRoot.StartsWith($tempRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $qaRoot)) { throw 'Output must be new and below RUNNER_TEMP.' }
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source
Import-Module (Join-Path $PSScriptRoot 'OwnProcessJob.psm1') -Force
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$record = [ordered]@{schema_version=1;status='running';controller_pid=$PID;python_exit_code=$null;errors=@();drain=$null;close=$null}
$job = $null
$exitStatus = 1
try {
    $job = New-OwnedProcessJob
    $env:CADENCE_AUDIO_QA_OWNED_JOB = [string]$PID
    & $python -I -B -X utf8 (Join-Path $PSScriptRoot 'qualify_audio_transcription.py') `
        --executable $Executable --expected-executable-sha256 $ExpectedExecutableSha256 `
        --engine-executable $EngineExecutable --ctest-log $CtestLog `
        --build-state $BuildState --build-result $BuildResult --engine-build-receipt $EngineBuildReceipt --output (Join-Path $qaRoot 'runtime') `
        1> (Join-Path $qaRoot 'probe.stdout.log') 2> (Join-Path $qaRoot 'probe.stderr.log')
    $record.python_exit_code = $LASTEXITCODE
    Get-Content -LiteralPath (Join-Path $qaRoot 'probe.stdout.log') | Write-Host
    Get-Content -LiteralPath (Join-Path $qaRoot 'probe.stderr.log') | Write-Host
    if ($record.python_exit_code -ne 0) { throw 'Windows native engine/import probe failed.' }
    $exitStatus = 0
} catch {
    $record.errors += $_.Exception.Message
} finally {
    if ($null -ne $job) {
        try {
            $record.drain = Stop-OwnedJobChildren -Job $job -TimeoutMilliseconds 20000
            if (-not $record.drain.ChildrenDrained -or @($record.drain.TerminatedPids).Count -ne 0) {
                throw 'Owned children did not exit naturally; this QA cannot pass.'
            }
        } catch { $record.errors += $_.Exception.Message; $exitStatus = 1 }
        # Close is the final operation that can affect processes. No new process
        # may be started after this point; only serialize evidence and exit pwsh.
        try { $record.close = Close-OwnedProcessJob -Job $job }
        catch { $record.errors += $_.Exception.Message; $exitStatus = 1 }
    }
    if ($record.errors.Count -ne 0) { $exitStatus = 1 }
    $record.status = if ($exitStatus -eq 0) { 'passed-natural-exits-and-owned-Job-drained' } else { 'failed-or-blocked' }
    $record | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $qaRoot 'owned-job-report.json') -Encoding utf8NoBOM
    Write-Host ('CADENCE_AUDIO_OWNED_JOB ' + ($record | ConvertTo-Json -Depth 10 -Compress))
}
exit $exitStatus
