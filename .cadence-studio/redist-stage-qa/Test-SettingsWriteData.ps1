# SPDX-License-Identifier: GPL-3.0-only
# Execute only the exact bounded, exclusive settings-write AST on synthetic files.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'Invoke-IcuOmission.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'The actual wrapper does not parse.'}
$blocks=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.TryStatementAst] -and $node.Extent.Text.StartsWith('try{') -and $node.Extent.Text.Contains('$settingsStream.Length -gt 2097152') -and -not $node.Extent.Text.Contains('Import-Module')},$true))
if($blocks.Count -ne 1){throw 'The exclusive bounded writer is not unique.'}
$block=[scriptblock]::Create($blocks[0].Extent.Text)
$directory=Join-Path ([IO.Path]::GetTempPath()) ('cadence-icu-settings-synthetic-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($directory)
$results=@()
try{
    foreach($case in @('valid','changed-seed','oversized')){
        $path=Join-Path $directory ($case+'.ini')
        $seed=[Text.Encoding]::UTF8.GetBytes('synthetic initial ASIO profile')
        [IO.File]::WriteAllBytes($path,$seed)
        $profileState=@{seed_settings_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($seed)).ToLowerInvariant()}
        if($case -eq 'changed-seed'){[IO.File]::WriteAllText($path,'changed before exclusive open')}
        if($case -eq 'oversized'){[IO.File]::WriteAllBytes($path,[byte[]]::new(2097153))}
        $before=(Get-FileHash -LiteralPath $path).Hash
        $converterSettings=[Text.Encoding]::UTF8.GetBytes('synthetic WASAPI/default replacement')
        $settingsStream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        $accepted=$false
        try{. $block;$accepted=$true}catch{}
        if($case -eq 'valid'){
            if(-not $accepted -or [IO.File]::ReadAllText($path) -cne 'synthetic WASAPI/default replacement'){throw 'Valid exclusive writer failed.'}
        }elseif($accepted -or (Get-FileHash -LiteralPath $path).Hash -cne $before){throw 'Invalid seed was accepted or changed.'}
        $results+=@{case=$case;passed=$true}
    }
}finally{[IO.Directory]::Delete($directory,$true)}
$report=@{schema_version=1;scope='Actual bounded writer AST on synthetic temporary INI files under Linux; no KnownFolders, application, registry or Windows API';cases_passed=$results.Count;results=$results}
$report|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'settings-writer-synthetic-results.json') -Encoding utf8NoBOM
$report|ConvertTo-Json -Depth 6 -Compress
