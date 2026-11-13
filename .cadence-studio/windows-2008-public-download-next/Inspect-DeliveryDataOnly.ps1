# SPDX-License-Identifier: GPL-3.0-only
# Run in a disposable Windows Actions job with contents:read/actions:read only.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$WorkDirectory,[Parameter(Mandatory)][string]$OutputPath)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($env:OS-ne'Windows_NT'-or-not[Environment]::Is64BitProcess-or$env:GITHUB_ACTIONS-ne'true'-or$env:RUNNER_ENVIRONMENT-ne'github-hosted'-or-not$env:GH_TOKEN){throw 'Disposable Windows Actions environment and ephemeral read token are required.'}
python -I "$PSScriptRoot/inspect_delivery.py" --work $WorkDirectory --output $OutputPath
if($LASTEXITCODE-ne0){throw 'The producer is incomplete or its real data did not pass inspection. No target or GitHub write was created.'}
