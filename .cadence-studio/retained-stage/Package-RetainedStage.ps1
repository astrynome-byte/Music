# SPDX-License-Identifier: GPL-3.0-only
# Repackage an authenticated retained CI stage; never compile an application payload.
#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $SourcePath,
    [Parameter(Mandatory)][string] $BootstrapResultPath,
    [Parameter(Mandatory)][string] $StageArtifactPath,
    [Parameter(Mandatory)][string] $OutputPath,
    [switch] $VerifyOnly,
    [switch] $ConfigureOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$expectedTree = '65322ea3a3fbb419695a9b226607153b1c698886'
$originalSourceCommit = '24cce38f0fea7d976382bb09e54d90415c9de6c4'
$upstreamCommit = '96480d58445e3b24b230a3fe7d4725d639aa2eb3'
$retainedCiCommit = 'a8f2b2432502ba044c7be1b758b30d7fddaedba3'
$retainedArchiveHash = 'ff8c5f050bb61e1e8de77ca1b3161a226095efbcd7c03d31ac09f2557d3cf1ed'
$retainedExecutableHash = '62987537161d89d9d0f2da6b9915b7f421a9718e288d7aa84a6b3f7dacfc0a34'
if ($VerifyOnly -and $ConfigureOnly) { throw 'Choose VerifyOnly or ConfigureOnly.' }
if (-not $VerifyOnly -and -not $ConfigureOnly) {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
        $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
        throw 'Packaging is restricted to disposable native Windows x64 GitHub-hosted runners.'
    }
}
if (-not $env:RUNNER_TEMP) { throw 'RUNNER_TEMP is required, including read-only verification tests.' }
function FullPath([string] $Value) {
    if ($Value -match '[;\r\n"]') { throw 'A path contains an unsupported CMake/list or command character.' }
    [IO.Path]::GetFullPath($Value)
}
$SourcePath = FullPath $SourcePath
$StageArtifactPath = FullPath $StageArtifactPath
$BootstrapResultPath = FullPath $BootstrapResultPath
$OutputPath = FullPath $OutputPath
$temporaryRoot = (FullPath $env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputPath.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'OutputPath must be strictly below RUNNER_TEMP.' }
if (Test-Path -LiteralPath $OutputPath) { throw 'OutputPath must be new; no existing files are replaced.' }
foreach ($protected in @($SourcePath, $StageArtifactPath)) {
    if ($OutputPath.StartsWith($protected.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'OutputPath must be outside the source and original artifact.' }
}
function GitText([string[]] $Arguments) {
    $text = @(& git -C $SourcePath @Arguments)
    if ($LASTEXITCODE -ne 0) { throw 'Git source verification failed.' }
    ($text -join "`n").Trim()
}
function Assert-Source {
    if ((GitText @('rev-parse', 'HEAD^{tree}')) -ne $expectedTree -or
        (GitText @('status', '--porcelain', '--untracked-files=all'))) {
        throw 'Source must be clean and match the exact audited source tree; no payload was rebuilt.'
    }
}
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Read-Json([string] $Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Write-Json($Value, [string] $Path) { $Value | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $Path -Encoding utf8 }
function Native([string] $Tool, [string[]] $Arguments, [string] $Log) {
    $command = (Get-Command $Tool -ErrorAction Stop).Source
    Write-Host ($Tool + ' ' + ($Arguments -join ' '))
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $command @Arguments 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($code -ne 0) { throw "$Tool failed with exit status $code; see $Log" }
}
# All checks through the ZIP directory inspection are read-only and happen before
# creating OutputPath, extracting files, or executing anything from the stage.
Assert-Source
$currentCommit = GitText @('rev-parse', 'HEAD')
$bootstrap = Read-Json $BootstrapResultPath
if ($bootstrap.schema_version -ne 1 -or $bootstrap.source_tree -ne $expectedTree -or
    $bootstrap.original_source_commit -ne $originalSourceCommit -or $bootstrap.ci_source_commit -ne $currentCommit -or
    $bootstrap.upstream_commit -ne $upstreamCommit -or (FullPath $bootstrap.source_path) -ne $SourcePath) {
    throw 'Bootstrap record does not authenticate this exact reconstructed source.'
}
$checksums = @{}
foreach ($line in Get-Content -LiteralPath (Join-Path $StageArtifactPath 'SHA256SUMS.txt')) {
    if ($line -notmatch '^([a-fA-F0-9]{64})  (.+)$') { throw 'Malformed artifact checksum line.' }
    $digest = $Matches[1].ToLowerInvariant(); $name = $Matches[2]
    if ($name -match '[/\\:]' -or $name -in @('.', '..', 'SHA256SUMS.txt') -or $checksums.ContainsKey($name)) { throw 'Unsafe or duplicate artifact checksum name.' }
    $file = Join-Path $StageArtifactPath $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Hash $file) -ne $digest) { throw "Artifact SHA-256 mismatch: $name" }
    $checksums[$name] = $digest
}
foreach ($file in Get-ChildItem -LiteralPath $StageArtifactPath -Force) {
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Artifact must contain only ordinary root files.' }
    if ($file.Name -ne 'SHA256SUMS.txt' -and -not $checksums.ContainsKey($file.Name)) { throw 'Artifact contains a file not covered by SHA256SUMS.' }
}
foreach ($name in @('stage-manifest.json', 'cadence-build.json', 'cadence-build-result.json', 'dependencies.lock.json')) {
    if (-not $checksums.ContainsKey($name)) { throw "Required authenticated record missing: $name" }
}
$manifest = Read-Json (Join-Path $StageArtifactPath 'stage-manifest.json')
$state = Read-Json (Join-Path $StageArtifactPath 'cadence-build.json')
$result = Read-Json (Join-Path $StageArtifactPath 'cadence-build-result.json')
$lock = Read-Json (Join-Path $StageArtifactPath 'dependencies.lock.json')
if ($manifest.schema_version -ne 1 -or $manifest.variant -ne 'Cadence' -or $state.variant -ne 'Cadence' -or
    $state.schema_version -ne 1 -or $result.schema_version -ne 1 -or
    $manifest.source_tree -ne $expectedTree -or $manifest.source_commit -ne $retainedCiCommit -or
    $manifest.source_commit -ne $state.source_commit -or $manifest.source_commit -ne $result.source_commit -or
    $state.source_dirty_at_configure -or $result.source_dirty_at_build -or
    $manifest.configuration -ne 'Release' -or $state.configuration -ne 'Release' -or
    $manifest.build_number -ne 7 -or $state.build_number -ne 7 -or $manifest.run_number -ne 7 -or $manifest.run_attempt -ne 1 -or
    $manifest.upstream_commit -ne $upstreamCommit -or $manifest.upstream_tag -ne 'v4.7.6' -or
    $lock.upstream.commit -ne $upstreamCommit -or $lock.qt.version -ne '6.10.2' -or
    $manifest.qt_version -ne $lock.qt.version -or $state.qt_version -ne $lock.qt.version) {
    throw 'Retained stage records do not identify the clean audited Cadence release build 7.'
}
if ((Hash (Join-Path $SourcePath 'scripts/config/dependencies.lock.json')) -ne $checksums['dependencies.lock.json']) { throw 'Stage dependency lock differs from the audited source.' }
if ($manifest.executable_sha256 -ne $retainedExecutableHash -or $result.executable_sha256 -ne $manifest.executable_sha256 -or
    [IO.Path]::GetFileName(($result.executable -replace '\\', '/')) -ne 'CadenceStudio4.exe') { throw 'Retained executable identity is inconsistent.' }
$archiveName = [string]$manifest.stage_archive
if (-not $checksums.ContainsKey($archiveName) -or $archiveName -notmatch '\.zip$' -or
    $checksums[$archiveName] -ne $manifest.stage_archive_sha256 -or
    $checksums[$archiveName] -ne $retainedArchiveHash -or
    @(Get-ChildItem -LiteralPath $StageArtifactPath -File -Filter '*.zip').Count -ne 1) { throw 'Retained archive identity is inconsistent.' }
$archive = Join-Path $StageArtifactPath $archiveName
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    [long]$expanded = 0; $hasExecutable = $false
    foreach ($entry in $zip.Entries) {
        $name = $entry.FullName.Replace('\', '/')
        while ($name.StartsWith('./')) { $name = $name.Substring(2) }
        if ($name -in @('', '.', '/')) { continue }
        $name = $name.TrimEnd('/')
        if ($name.StartsWith('/') -or $name.Contains(':') -or $name.Split('/') -contains '..' -or
            -not $names.Add($name) -or (($entry.ExternalAttributes -shr 16) -band 61440) -eq 40960 -or
            ($entry.ExternalAttributes -band 1024)) { throw 'Unsafe, linked or duplicate ZIP member.' }
        $expanded += $entry.Length
        if ($expanded -gt 5368709120 -or $zip.Entries.Count -gt 100000) { throw 'Retained ZIP exceeds extraction bounds.' }
        if ($name -eq 'bin/CadenceStudio4.exe' -and $entry.Length -gt 0) { $hasExecutable = $true }
    }
    if (-not $hasExecutable) { throw 'Archive does not contain the real staged Cadence executable.' }
} finally { $zip.Dispose() }
if ($VerifyOnly) { Write-Host 'PASS: read-only provenance, checksum, source tree and archive preflight. No extraction, native run or packaging happened.'; return }

$work = Join-Path $env:RUNNER_TEMP ('cadence-retained-' + [guid]::NewGuid())
$project = Join-Path $work 'packaging-project'; $build = Join-Path $work 'packaging-build'; $stage = Join-Path $work 'verified-stage'
$assets = @('buildscripts/packaging/Windows/Installer/WIX.template.in', 'buildscripts/packaging/Windows/Installer/LICENSE.rtf',
    'buildscripts/packaging/Windows/Installer/installer_banner_wix.png', 'buildscripts/packaging/Windows/Installer/installer_background_wix.png', 'share/icons/AppIcon/MS4_AppIcon.ico')
New-Item -ItemType Directory -Path $OutputPath, $project, $build, $stage | Out-Null
$report = [ordered]@{
    schema_version = 1; status = 'pending'; operation = 'Repackage retained real stage; no application rebuild'
    original_source_commit = $originalSourceCommit; payload_source_commit = $manifest.source_commit; payload_source_tree = $expectedTree
    packaging_source_commit = $currentCommit; packaging_source_tree = $expectedTree; build_number = 7
    original_stage_archive = $archiveName; original_stage_archive_sha256 = $checksums[$archiveName]
    original_run_number = 7; original_run_attempt = $manifest.run_attempt
    work_path = $work; extracted_stage = $stage; application_recompiled = $false
    native_version_checked = $false; windows_installation_tested = $false; gui_tested = $false; musical_listening_completed = $false
    source_unchanged = $false; payload_unchanged = $false; transitive_license_audit = 'open'
    signature = 'unsigned'; publication_url = $null; asset_sha256 = @{}; error = $null
}
function Stage-Inventory {
    $items = [ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -Force | Sort-Object FullName) {
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Extracted stage has a reparse point.' }
        if (-not $file.PSIsContainer) { $items[[IO.Path]::GetRelativePath($stage, $file.FullName)] = Hash $file.FullName }
    }
    $items
}
try {
    $originals = Join-Path $OutputPath 'original-stage'
    New-Item -ItemType Directory -Path $originals | Out-Null
    foreach ($file in Get-ChildItem -LiteralPath $StageArtifactPath -File) {
        Copy-Item -LiteralPath $file.FullName -Destination $originals
        if ((Hash (Join-Path $originals $file.Name)) -ne (Hash $file.FullName)) { throw 'Original provenance copy changed.' }
    }
    Copy-Item -LiteralPath $BootstrapResultPath -Destination (Join-Path $OutputPath 'packaging-bootstrap.json')
    Expand-Archive -LiteralPath $archive -DestinationPath $stage
    $exe = Join-Path $stage 'bin/CadenceStudio4.exe'
    if ((Hash $exe) -ne $manifest.executable_sha256) { throw 'Extracted executable SHA-256 mismatch; nothing from the stage was executed.' }
    if ((Get-Item -LiteralPath $exe).Length -ne 79583744) { throw 'Retained executable length differs from the inspected run 7 payload.' }
    $payloadBefore = Stage-Inventory
    Write-Json $payloadBefore (Join-Path $OutputPath 'stage-file-sha256.json')
    # The projection is explicitly a relocation of an ORIGINAL build result. It
    # is never passed through Build.ps1 and does not claim a new compilation.
    $verification = [ordered]@{
        schema_version = 1; record_kind = 'retained-stage-relocation-verification-not-a-new-build'
        source_commit = $result.source_commit; source_dirty_at_build = $result.source_dirty_at_build
        original_built_utc = $result.built_utc; original_executable_path = $result.executable
        executable = $exe; executable_sha256 = $manifest.executable_sha256; source_tree = $expectedTree
        original_result_sha256 = $checksums['cadence-build-result.json']; original_result_file = 'original-stage/cadence-build-result.json'
        verified_utc = [DateTime]::UtcNow.ToString('o'); application_recompiled = $false; windows_runtime_tested = $false
    }
    Write-Json $verification (Join-Path $OutputPath 'stage-verification-result.json')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'CMakeLists.txt') -Destination $project
    foreach ($relative in $assets) {
        $original = Join-Path $SourcePath $relative; $copy = Join-Path $project $relative
        New-Item -ItemType Directory -Path (Split-Path $copy) -Force | Out-Null
        Copy-Item -LiteralPath $original -Destination $copy
        $digest = Hash $original
        if ((Hash $copy) -ne $digest) { throw 'A packaging asset changed during copy.' }
        $report.asset_sha256[$relative] = $digest
    }
    $arguments = @('-S', $project, '-B', $build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_BUILD_NUMBER=7',
        "-DCADENCE_SOURCE_ROOT=$SourcePath", "-DCADENCE_STAGE_ROOT=$stage", "-DCMAKE_INSTALL_PREFIX=$stage", '-DMUE_PACK_INSTALL_DIR=ON')
    if ($ConfigureOnly) { $arguments += '-DCADENCE_RETAINED_CONFIGURE_ONLY=ON' }
    else { $arguments += '-DCMAKE_CXX_COMPILER=cl.exe' }
    Native cmake $arguments (Join-Path $OutputPath 'packaging-configure.log')
    if ($ConfigureOnly) {
        $report.status = 'configuration-only-no-msi-no-native-execution'
    } else {
        # Check PE machine before execution; the authenticated executable must
        # be Windows AMD64. The source CLI reports revision, not numeric build 7.
        $stream = [IO.File]::OpenRead($exe); $reader = [IO.BinaryReader]::new($stream)
        try {
            if ($reader.ReadUInt16() -ne 23117) { throw 'Staged executable lacks DOS signature.' }
            $stream.Position = 60; $peOffset = $reader.ReadUInt32()
            if ($peOffset -gt $stream.Length - 26) { throw 'Invalid PE header offset.' }
            $stream.Position = $peOffset
            if ($reader.ReadUInt32() -ne 17744 -or $reader.ReadUInt16() -ne 34404) { throw 'Staged executable is not PE AMD64.' }
        } finally { $reader.Dispose(); $stream.Dispose() }
        $start = [Diagnostics.ProcessStartInfo]::new(); $start.FileName = $exe
        $start.WorkingDirectory = Join-Path $stage 'bin'; $start.ArgumentList.Add('--long-version')
        $start.UseShellExecute = $false; $start.CreateNoWindow = $true; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
        $start.Environment['PATH'] = (Join-Path $stage 'bin') + ';' + (Join-Path $env:SystemRoot 'System32')
        foreach ($name in @($start.Environment.Keys)) {
            if ($name -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|FrameworkDir|FrameworkVersion)') { [void]$start.Environment.Remove($name) }
        }
        $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
        try {
            if (-not $process.Start()) { throw 'Retained executable did not start.' }
            $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
            if (-not $process.WaitForExit(60000)) { $process.Kill($true); $process.WaitForExit(); throw 'Retained version check timed out.' }
            $text = $stdout.GetAwaiter().GetResult() + "`n" + $stderr.GetAwaiter().GetResult()
            [IO.File]::WriteAllText((Join-Path $OutputPath 'retained-long-version.log'), $text)
            if ($process.ExitCode -ne 0 -or $text -notmatch '(?i)Version\s+4\.7\.6(?:\D|$)' -or
                $text -notmatch ('(?i)Build\s+' + [regex]::Escape($manifest.source_commit.Substring(0, 7)) + '(?:[a-f0-9]*)(?:\D|$)')) { throw 'Retained native version/revision did not match the archived build.' }
        } finally { $process.Dispose() }
        $report.native_version_checked = $true
        Assert-Source
        Native cpack @('--config', (Join-Path $build 'CPackConfig.cmake'), '-G', 'WIX', '-C', 'Release', '-B', $OutputPath, '--verbose') (Join-Path $OutputPath 'package.log')
        $msis = @(Get-ChildItem -LiteralPath $OutputPath -File -Filter '*.msi')
        if ($msis.Count -ne 1) { throw 'Expected one MSI from the retained real stage.' }
        $report['installer'] = $msis[0].Name; $report['installer_sha256'] = Hash $msis[0].FullName
        Native git @('-C', $SourcePath, 'archive', '--format=tar.gz', "--output=$(Join-Path $OutputPath 'CadenceStudio-4.7.6-cadence.7-source.tar.gz')", $expectedTree) (Join-Path $OutputPath 'source-archive.log')
        Native git @('-C', $SourcePath, 'diff', '--binary', '--full-index', "--output=$(Join-Path $OutputPath 'CadenceStudio-4.7.6-cadence.7-from-upstream.patch')", $upstreamCommit, $expectedTree) (Join-Path $OutputPath 'source-archive.log')
        foreach ($name in @('LICENSE.txt', 'README.md', 'FEATURES.md', 'STATUS.md', 'ROADMAP.md')) { Copy-Item -LiteralPath (Join-Path $SourcePath $name) -Destination $OutputPath }
        Copy-Item -LiteralPath (Join-Path $SourcePath 'scripts/config/dependencies.lock.json') -Destination $OutputPath
        @'
# Cadence Studio 4.7.6 — build Cadence 7 expérimental

Ce MSI réempaquette le véritable stage Windows x64 déjà compilé du run 7.
Aucune recompilation de l'application n'a été réalisée pour cet empaquetage.
Les sources fournies correspondent à l'arbre source exact du programme ; leurs
README et états historiques sont conservés sans modification.

Ce paquet n'est pas encore le cadeau final. La qualification de l'installateur,
les essais de l'interface graphique et les écoutes musicales sont suivis
séparément : consulter retained-package-manifest.json et les rapports de recette.
Aucun lien de téléchargement public ni publication n'est créé par cette étape.

SHA256SUMS.txt identifie par SHA-256 les livrables et les enregistrements
originaux. Ces empreintes ne constituent pas une signature Windows. Le dossier
original-stage conserve les pièces d'origine ; les intermédiaires internes
_CPack_Packages ne font pas partie des livrables. L'audit des licences et sources
des dépendances transitives reste ouvert avant une distribution finale.

L'objectif de la livraison finale est une installation simple chez l'ami,
sans SDK Qt, compilateur MSVC ni autre outil de développement. La vérification
de cette autonomie sur une machine Windows destinée à l'utilisateur reste une
étape distincte de la fabrication du paquet expérimental.
'@ | Set-Content -LiteralPath (Join-Path $OutputPath 'EXPERIMENTAL.md') -Encoding utf8
        $report.status = 'experimental-repackaged-awaiting-real-installation-and-license-audit'
    }
    if ((ConvertTo-Json $payloadBefore -Compress -Depth 4) -ne (ConvertTo-Json (Stage-Inventory) -Compress -Depth 4)) { throw 'Retained payload changed during verification or packaging.' }
    $report.payload_unchanged = $true
} catch {
    $report.status = 'failed'; $report.error = $_.Exception.Message
    foreach ($log in @(Get-ChildItem -LiteralPath $OutputPath -Recurse -File -Filter 'wix.log' -ErrorAction SilentlyContinue)) { Get-Content -LiteralPath $log.FullName | Out-Host }
    throw
} finally {
    try {
        Assert-Source
        if ((GitText @('rev-parse', 'HEAD')) -ne $currentCommit) { throw 'Source commit changed during retained-stage packaging.' }
        $report.source_unchanged = $true
    } catch { $report.status = 'failed'; $report.error = $_.Exception.Message; throw }
    finally { Write-Json $report (Join-Path $OutputPath 'retained-package-manifest.json') }
}
Get-ChildItem -LiteralPath $OutputPath -File -Recurse | Where-Object {
    ([IO.Path]::GetRelativePath($OutputPath, $_.FullName) -replace '\\', '/') -notmatch '^_CPack_Packages/'
} | Sort-Object FullName | ForEach-Object {
    '{0}  {1}' -f (Hash $_.FullName), ([IO.Path]::GetRelativePath($OutputPath, $_.FullName) -replace '\\', '/')
} | Set-Content -LiteralPath (Join-Path $OutputPath 'SHA256SUMS.txt') -Encoding ascii
Write-Host "Retained stage result: $($report.status). No application was rebuilt or published."
