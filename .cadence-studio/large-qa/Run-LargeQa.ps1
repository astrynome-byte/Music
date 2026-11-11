# SPDX-License-Identifier: GPL-3.0-only
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $StagePath,
    [Parameter(Mandatory)][string] $RestorationRecordPath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# This guard precedes all filesystem writes and child processes.
if (-not [OperatingSystem]::IsWindows() -or $env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Only disposable native Windows x64 GitHub-hosted runners are permitted.'
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required.' }
# Python is supplied by setup-python, never inherited by the Cadence process PATH.
& python -X utf8 -I -B "$PSScriptRoot/run_large_qa.py" `
    --stage $StagePath --restoration-record $RestorationRecordPath --output $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw "Large-score smoke failed or was blocked (Python exit $LASTEXITCODE)." }
