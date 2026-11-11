# SPDX-License-Identifier: GPL-3.0-only
# Exercise the actual build-script functions without running its Windows build.
#Requires -Version 7.0
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$scriptPath = Join-Path $PSScriptRoot '../Build-Windows.ps1'
$ast = [Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw "Build script parse failed: $errors" }
$definitions = @($ast.FindAll({
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in @('ToolPath', 'Native')
}, $true))
if ($definitions.Count -ne 2) { throw 'Expected the actual ToolPath and Native function definitions.' }
foreach ($definition in $definitions) { . ([scriptblock]::Create($definition.Extent.Text)) }

$WorkPath = Join-Path ([IO.Path]::GetTempPath()) ('zlib tool path regression ' + [guid]::NewGuid())
$first = Join-Path $WorkPath 'first CMake installation'
$second = Join-Path $WorkPath 'second CMake installation'
$previousPath = $env:PATH
$callerExitVariable = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
$callerExitValue = if ($null -ne $callerExitVariable) { $callerExitVariable.Value } else { $null }
New-Item -ItemType Directory -Path $WorkPath, $first, $second | Out-Null
try {
    if ($env:OS -eq 'Windows_NT') {
        $commandName = 'cmake.cmd'
        "@echo off`r`nif not `"%~1`"==`"directory with spaces`" exit /b 9`r`necho PRIMARY_CMAKE_SHIM`r`nexit /b 0`r`n" | Set-Content (Join-Path $first $commandName) -Encoding ascii
        "@echo off`r`necho WRONG_SECONDARY_CMAKE`r`nexit /b 7`r`n" | Set-Content (Join-Path $second $commandName) -Encoding ascii
    } else {
        $commandName = 'cmake'
        @'
#!/bin/sh
[ "$1" = "directory with spaces" ] || exit 9
printf '%s\n' PRIMARY_CMAKE_SHIM
exit 0
'@ | Set-Content (Join-Path $first $commandName) -Encoding ascii
        "#!/bin/sh`nprintf '%s\n' WRONG_SECONDARY_CMAKE`nexit 7`n" | Set-Content (Join-Path $second $commandName) -Encoding ascii
        & chmod +x (Join-Path $first $commandName) (Join-Path $second $commandName)
        if ($LASTEXITCODE -ne 0) { throw 'Cannot make the Linux-only command fixtures executable.' }
    }
    $env:PATH = $first + [IO.Path]::PathSeparator + $second + [IO.Path]::PathSeparator + $previousPath
    $script:toolCandidates = @(Microsoft.PowerShell.Core\Get-Command cmake -CommandType Application -All -ErrorAction Stop |
        Where-Object Source -in @((Join-Path $first $commandName), (Join-Path $second $commandName)))
    if ($script:toolCandidates.Count -ne 2) { throw 'Both homonymous applications must be discoverable in separate spaced paths.' }
    # Some hosts enumerate both CMake installations. Return the real discovered
    # CommandInfo objects together to cover that case on every test platform.
    function Get-Command {
        [CmdletBinding()]
        param([string] $Name, [object] $CommandType, [switch] $All)
        if ($Name -eq 'cmake') { return $script:toolCandidates }
        Microsoft.PowerShell.Core\Get-Command @PSBoundParameters
    }
    $selected = @(ToolPath cmake)
    if ($selected.Count -ne 1 -or $selected[0] -ne (Join-Path $first $commandName)) { throw 'Tool resolution did not select one first executable.' }
    $commands = [Collections.Generic.List[object]]::new()
    $log = Join-Path $WorkPath 'native command with spaces.log'
    Native cmake @('directory with spaces') $log
    $text = Get-Content -LiteralPath $log -Raw
    if ($text -notmatch 'PRIMARY_CMAKE_SHIM' -or $text -match 'WRONG_SECONDARY_CMAKE') { throw 'The actual Native function executed the wrong tool.' }
    $record = @(Get-Content (Join-Path $WorkPath 'commands.json') -Raw | ConvertFrom-Json)
    if ($record.Count -ne 1 -or $record[0].executable -ne $selected[0] -or $record[0].arguments[0] -ne 'directory with spaces') { throw 'Exact tool path/arguments were not preserved in the real command record.' }
    $rejected = $false
    try { Native cmake @('incorrect argument') (Join-Path $WorkPath 'native-failure.log') }
    catch { if ($_.Exception.Message -match 'exit code 9') { $rejected = $true } else { throw } }
    if (-not $rejected) { throw 'The actual Native function ignored a nonzero exit status.' }
    $rejected = $false
    try { [void](ToolPath ('missing-zlib-profile-tool-' + [guid]::NewGuid())) } catch { $rejected = $true }
    if (-not $rejected) { throw 'Missing executable discovery did not throw.' }
    Write-Host 'PASS: actual Native/ToolPath AST, two CMake installations in spaced paths, first-tool selection, exact arguments, nonzero status and missing-tool rejection.'
    Write-Host 'This is a tool-resolution regression test; it does not compile zlib or validate Windows.'
} finally {
    $env:PATH = $previousPath
    try { Remove-Item -LiteralPath $WorkPath -Recurse -Force }
    finally {
        # Expected failing native commands must not poison the enclosing Actions
        # step, whose pwsh wrapper propagates LASTEXITCODE after this script.
        # Restore caller state rather than exit 0: real assertion failures remain
        # terminating errors and must still fail the surrounding step.
        if ($null -ne $callerExitVariable) { $global:LASTEXITCODE = $callerExitValue }
        else { Remove-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue }
    }
}
