# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Executable,
    [Parameter(Mandatory)][string] $ProbePath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT' -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'The clean GUI probe is restricted to disposable hosted Windows CI.'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'GUI output directory must be new.' }
$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = (Get-Process -Id $PID).Path
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
foreach ($arg in @('-NoLogo', '-NoProfile', '-NonInteractive', '-File', $ProbePath, '-Executable', $Executable, '-OutputDirectory', $OutputDirectory)) {
    $start.ArgumentList.Add($arg)
}
$start.Environment['PATH'] = (Split-Path -Parent $Executable) + ';' + (Join-Path $env:SystemRoot 'System32')
foreach ($key in @($start.Environment.Keys)) {
    if ($key -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$)') {
        [void]$start.Environment.Remove($key)
    }
}
$process = [Diagnostics.Process]::new()
$process.StartInfo = $start
try {
    if (-not $process.Start()) { throw 'GUI test process could not start.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(90000)) {
        $process.Kill($true)
        $process.WaitForExit()
        throw 'GUI test exceeded 90 seconds; its owned process tree was stopped.'
    }
    $outText = $stdout.GetAwaiter().GetResult()
    $errText = $stderr.GetAwaiter().GetResult()
    Write-Host $outText
    if ($errText) { Write-Host $errText }
    if (Test-Path -LiteralPath $OutputDirectory) {
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe-wrapper.stdout.log'), $outText)
        [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe-wrapper.stderr.log'), $errText)
    }
    if ($process.ExitCode -eq 2) {
        Write-Warning 'GUI observation was blocked by the hosted desktop/session. GUI remains unvalidated; inspect gui-report.json.'
    } elseif ($process.ExitCode -ne 0) {
        throw "GUI startup/cleanup probe failed with exit code $($process.ExitCode)."
    }
} finally { $process.Dispose() }
