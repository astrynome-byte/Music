# SPDX-License-Identifier: GPL-3.0-only
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
python -I (Join-Path $PSScriptRoot 'check_retained_configuration.py') --temporary-root $env:RUNNER_TEMP --source-root (Join-Path $env:GITHUB_WORKSPACE 'cadence-src') --output (Join-Path $env:RUNNER_TEMP 'retained-configuration.json')
if ($LASTEXITCODE -ne 0) { throw 'Regenerated configuration differs from the original application build' }
