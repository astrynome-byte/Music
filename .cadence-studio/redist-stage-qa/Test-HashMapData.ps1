# SPDX-License-Identifier: GPL-3.0-only
# Execute only the real pure-data Assert-HashMap AST from the Windows wrapper.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$errors=$null;$tokens=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'Invoke-IcuOmission.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'The actual wrapper does not parse.'}
$functions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-HashMap'},$true))
if($functions.Count -ne 1){throw 'The actual data guard function is not unique.'}
. ([scriptblock]::Create($functions[0].Extent.Text))
$expected=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
$expected.Add('bin/icuuc.dll','icu-sha');$expected.Add('bin/Qt6Core.dll','qt-sha');$expected.Add('bin/dxil.dll','dxil-sha')
function Candidate([string]$Mode){
    $value=[Collections.Generic.Dictionary[string,string]]::new($expected,[StringComparer]::Ordinal)
    switch($Mode){
        'omit' {[void]$value.Remove('bin/icuuc.dll')}
        'changed' {$value['bin/dxil.dll']='changed'}
        'two-missing' {[void]$value.Remove('bin/icuuc.dll');[void]$value.Remove('bin/dxil.dll')}
        'wrong-missing' {[void]$value.Remove('bin/dxil.dll')}
        'extra' {$value.Add('bin/other.dll','unexpected')}
    };return $value
}
$cases=@(
    @{name='identical accepted';mode='same';except='';accept=$true},
    @{name='single ICU omission accepted';mode='omit';except='bin/icuuc.dll';accept=$true},
    @{name='non-ICU change refused';mode='changed';except='';accept=$false},
    @{name='two omissions refused';mode='two-missing';except='bin/icuuc.dll';accept=$false},
    @{name='wrong missing DLL refused';mode='wrong-missing';except='bin/icuuc.dll';accept=$false},
    @{name='still-present ICU refused';mode='same';except='bin/icuuc.dll';accept=$false},
    @{name='unexpected member refused';mode='extra';except='';accept=$false}
)
$results=@()
foreach($case in $cases){
    $accepted=$false
    try{Assert-HashMap $expected (Candidate $case.mode) $case.except;$accepted=$true}catch{}
    if($accepted -ne $case.accept){throw ('Incorrect guard outcome: '+$case.name)}
    $results+=@{case=$case.name;passed=$true}
}
$report=@{schema_version=1;scope='Actual PowerShell AST pure-data guard on Linux; no application, Windows API or file deletion';cases_passed=$results.Count;results=$results}
$report|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'hash-map-synthetic-results.json') -Encoding utf8NoBOM
$report|ConvertTo-Json -Depth 6 -Compress
