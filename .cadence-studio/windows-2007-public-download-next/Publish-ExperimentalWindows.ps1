# SPDX-License-Identifier: GPL-3.0-only
# Future reviewed experimental Windows publication only. No active target exists.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$TargetPath,
    [Parameter(Mandatory)][string]$InputRoot,
    [Parameter(Mandatory)][string]$AcquiredRoot,
    [Parameter(Mandatory)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($env:OS-ne'Windows_NT'-or-not[Environment]::Is64BitProcess-or$env:GITHUB_ACTIONS-ne'true'-or$env:CI-ne'true'-or$env:RUNNER_ENVIRONMENT-ne'github-hosted'-or$env:GITHUB_EVENT_NAME-ne'push'-or$env:GITHUB_REF-ne'refs/heads/cadence-studio/windows-build'){throw 'Only the explicit reviewed-target push on disposable hosted Windows CI may publish.'}
if(-not$env:GH_TOKEN-or-not$env:RUNNER_TEMP){throw 'The ephemeral repository token and RUNNER_TEMP are required.'}
. "$PSScriptRoot/Read-PublicationTransport.ps1"
$target=Read-PublicationTransport $TargetPath
$workflowHead=[string]$env:GITHUB_SHA
if($workflowHead-cnotmatch'^[a-f0-9]{40}$'){throw 'Actual current workflow GITHUB_SHA is required; no tag target is read from its own target document.'}
$AcquiredRoot=[IO.Path]::GetFullPath($AcquiredRoot);$InputRoot=[IO.Path]::GetFullPath($InputRoot);$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if(-not$AcquiredRoot.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase)-or-not$InputRoot.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase)-or-not$OutputDirectory.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase)-or(Test-Path $OutputDirectory)-or-not(Test-Path $InputRoot -PathType Container)) {throw 'Prepared sound assets and new publication evidence must be below RUNNER_TEMP.'}
$gh=(Get-Command gh -CommandType Application -ErrorAction Stop|Select-Object -First 1).Source
function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Invoke-ReleaseGh([string[]]$Arguments,[switch]$AllowNotFound){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$gh;$info.UseShellExecute=$false;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    [void]$info.Environment.Remove('GH_DEBUG')
    foreach($arg in $Arguments){$info.ArgumentList.Add($arg)}
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    try{
        if(-not$process.Start()){throw 'GitHub command did not start.'}
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if(-not$process.WaitForExit(900000)){$process.Kill($true);[void]$process.WaitForExit(5000);throw 'Owned GitHub operation timed out.'}
        $stdout=$out.GetAwaiter().GetResult();$stderr=$err.GetAwaiter().GetResult()
        if($stdout.Length-gt8388608-or$stderr.Length-gt32768){throw 'GitHub metadata output exceeds bounds.'}
        if($process.ExitCode-ne0){if($AllowNotFound-and$stderr-match'HTTP 404'){return $null};throw('GitHub operation failed without publishing approval: '+$stderr)}
        return $stdout.Trim()
    }finally{try{if($process.Id-and-not$process.HasExited){$process.Kill($true);[void]$process.WaitForExit(5000)}}catch{};$process.Dispose()}
}
function Get-ReleaseApi([string]$Endpoint,[switch]$AllowNotFound){
    $raw=Invoke-ReleaseGh @('api','--method','GET',$Endpoint) -AllowNotFound:$AllowNotFound
    if($null-eq$raw){return $null};return($raw|ConvertFrom-Json)
}
function Assert-AuditedMainBeforeMutation {
    $current=Get-ReleaseApi 'repos/astrynome-byte/Music/commits/main'
    if($current.sha-cne$target.android.main_commit){throw 'main changed before mutation; workflows require a fresh audit.'}
}
function Assert-NoExistingRelease([string]$Tag){
    # GET /releases/tags/:tag cannot resolve a draft whose tag is pending.
    # An authenticated list includes drafts: inspect a bounded complete list,
    # or refuse when its completeness cannot be established within that bound.
    for($page=1;$page-le20;$page++){
        $items=@(Get-ReleaseApi ('repos/astrynome-byte/Music/releases?per_page=100&page='+$page))
        if(@($items|Where-Object{$_.tag_name-ceq$Tag}).Count){throw 'This immutable Cadence release or draft already exists; it will not be edited or overwritten.'}
        if($items.Count-lt100){return}
    }
    throw 'Existing-release inventory exceeds the reviewed bound; no release will be created.'
}
function Get-WorkflowInventory([string]$Commit){
    $commitData=Get-ReleaseApi ('repos/astrynome-byte/Music/commits/'+$Commit)
    if($commitData.sha-cne$Commit){throw 'GitHub commit differs from the exact reviewed snapshot.'}
    $tree=Get-ReleaseApi ('repos/astrynome-byte/Music/git/trees/'+$commitData.commit.tree.sha+'?recursive=1')
    if($tree.truncated){throw 'Workflow tree was truncated; Android/tag triggers remain unreviewed.'}
    $items=@($tree.tree|Where-Object{$_.type-eq'blob'-and$_.path-cmatch'^\.github/workflows/[^/]+\.ya?ml$'}|Sort-Object path)
    if($items.Count-gt128){throw 'Workflow inventory exceeds the reviewed bound.'}
    return @($items|ForEach-Object{[ordered]@{path=$_.path;blob_sha1=$_.sha}})
}
function Assert-WorkflowInventory($Actual,$Expected){
    # OrderedDictionary and PSCustomObject do not expose identical sortable
    # properties. Compare the reviewed path->blob mapping, never sorted rows.
    $maps=@()
    foreach($side in @([pscustomobject]@{name='actual';items=@($Actual)},[pscustomobject]@{name='reviewed';items=@($Expected)})){
        if($side.items.Count-lt1-or$side.items.Count-gt128){throw ('Workflow inventory '+$side.name+' count outside 1..128; publication blocked.')}
        $map=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
        foreach($item in $side.items){
            if($item-is[Collections.IDictionary]){
                if(-not$item.Contains('path')-or-not$item.Contains('blob_sha1')){throw ('Workflow inventory '+$side.name+' has missing fields; publication blocked.')}
                $path=$item['path'];$sha=$item['blob_sha1']
            }elseif($item-is[pscustomobject]){
                if($null-eq$item.PSObject.Properties['path']-or$null-eq$item.PSObject.Properties['blob_sha1']){throw ('Workflow inventory '+$side.name+' has missing fields; publication blocked.')}
                $path=$item.path;$sha=$item.blob_sha1
            }else{throw ('Workflow inventory '+$side.name+' has an unsupported entry type; publication blocked.')}
            if($path-isnot[string]-or$path-cnotmatch'^\.github/workflows/[^/\\:\x00-\x1f]+\.ya?ml$'-or$sha-isnot[string]-or$sha-cnotmatch'^[a-f0-9]{40}$'){
                throw ('Workflow inventory '+$side.name+' has an invalid path/blob identity; publication blocked.')
            }
            if($map.ContainsKey($path)){throw ('Workflow inventory '+$side.name+' repeats path '+$path+'; publication blocked.')}
            $map.Add($path,$sha)
        }
        $maps+=,$map
    }
    $a=$maps[0];$e=$maps[1]
    if($a.Count-ne$e.Count){throw ('Workflow inventory count changed: actual='+$a.Count+', reviewed='+$e.Count+'; publication blocked.')}
    [string[]]$paths=@($e.Keys);[Array]::Sort($paths,[StringComparer]::Ordinal)
    foreach($path in $paths){
        if(-not$a.ContainsKey($path)){throw ('Reviewed workflow missing or renamed: '+$path+'; publication blocked.')}
        if(-not[StringComparer]::Ordinal.Equals($a[$path],$e[$path])){
            throw ('Reviewed workflow blob changed: '+$path+'; actual='+$a[$path]+', reviewed='+$e[$path]+'; publication blocked.')
        }
    }
}
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$report=[ordered]@{schema_version=1;status='failed';publicly_verified=$false;repository='astrynome-byte/Music';version=$target.version;tag=$target.release.tag;scope='Experimental Windows2007 MSI, exact application/component sources and notices';application_included=$true;limitations=$target.limitations
    source=$target.source;producer=$target.producer;producer_origin_verified=$false;tag_target_commit_mode='workflow_head';workflow_head=$workflowHead;tag_creation_attempted=$false;tag_created=$false;tag_cleanup=$null;draft_creation_attempted=$false;private_draft_outcome_unknown=$false;release_id=$null;release_url=$null;draft_created=$false;publication_attempted=$false;published=$false;withdrawn_after_failed_anonymous_verification=$false
    repository_visibility_verified=$false;android_main_and_tag_inventory_verified=$false;qualification=$null;assets=@();error=$null
    anonymous_client_credentials=$false;anonymous_authorization_header=$false;github_account_required_for_shared_link=$false;permanent_availability_promised=$false
    access_limit='Public GitHub release assets; availability depends on GitHub and retention by repository owner; no permanence promised.'}
$createdId=$null
try{
    python -I "$PSScriptRoot/windows_publication.py" validate --target $TargetPath --acquired $AcquiredRoot --root $InputRoot --output (Join-Path $OutputDirectory 'local-publication-validation.json')
    if($LASTEXITCODE-ne0){throw 'Actual full2007 MSI/source/notices/ICU prerequisites did not pass.'}
    $validation=Get-Content (Join-Path $OutputDirectory 'local-publication-validation.json') -Raw -Encoding utf8|ConvertFrom-Json
    if($validation.allowed-isnot[bool]-or-not$validation.allowed){throw 'Local publication validator did not approve.'}
    $report.qualification=$validation.actual_qualification
    $producerRun=Get-ReleaseApi ('repos/astrynome-byte/Music/actions/runs/'+$target.producer.run_id)
    Assert-PublicationProducerRunMetadata $producerRun $target
    foreach($id in @($target.artifacts|ForEach-Object{$_.id})){
        $producerArtifact=Get-ReleaseApi ('repos/astrynome-byte/Music/actions/artifacts/'+$id)
        Assert-PublicationProducerArtifactMetadata $producerArtifact $target
    }
    $report.producer_origin_verified=$true
    $headData=Get-ReleaseApi ('repos/astrynome-byte/Music/commits/'+$workflowHead)
    Assert-PublicationWorkflowHeadMetadata $headData $workflowHead
    $repo=Get-ReleaseApi 'repos/astrynome-byte/Music'
    if($repo.private-or$repo.visibility-cne'public'-or$repo.archived){throw 'Anonymous release hosting requires this exact active public repository.'}
    $report.repository_visibility_verified=$true
    $main=Get-ReleaseApi 'repos/astrynome-byte/Music/commits/main'
    if($main.sha-cne$target.android.main_commit){throw 'Android main changed since its explicit trigger review.'}
    Assert-WorkflowInventory (Get-WorkflowInventory $target.android.main_commit) $target.android.main_workflows
    Assert-WorkflowInventory (Get-WorkflowInventory $workflowHead) $target.android.tag_workflows
    $report.android_main_and_tag_inventory_verified=$true
    $encoded=[Uri]::EscapeDataString($target.release.tag)
    Assert-NoExistingRelease $target.release.tag
    if($null-ne(Get-ReleaseApi ('repos/astrynome-byte/Music/git/ref/tags/'+$encoded) -AllowNotFound)){throw 'This immutable tag already exists; no existing tag is moved.'}
    $notes=Join-Path $OutputDirectory 'RELEASE-NOTES-FR.md'
    @("Cadence Studio $($target.version) — préversion Windows 64 bits expérimentale.",
      "Cette livraison ne constitue pas le cadeau final et ne couvre pas encore tous les usages payants de l'écosystème de référence.",
      "MSI, source exacte de l'application, recette, sources correspondantes des composants, notices, guide français et SHA sont joints.",
      "Les Source code automatiques de GitHub désignent le dépôt pilote ; utilisez les archives source et composants jointes.",
      "Tests du vrai MSI et contrôles automatiques sur Windows Server 2022 CI ; clients Windows 10/11 et écoutes humaines non validés.",
      "Le profil GUI préparé ne valide pas le premier lancement neuf. Les fonctions et alternatives restent incomplètes ; voir FEATURES/STATUS/ROADMAP dans les sources.",
      "Liens sans compte vérifiés sur les vrais fichiers après publication ; aucune permanence d'hébergement garantie.")|Set-Content $notes -Encoding utf8
    # First create a private draft and upload the complete approved immutable set.
    # A failed upload cannot leave a supposedly complete public installer release.
    # Reuse the observed permission-probe sequence: a new tag at the triggering
    # workflow HEAD, then the empty private draft on that already-existing tag.
    # Build/source provenance stays pinned separately to the exact full2007 producer.
    $tagRequest=Join-Path $OutputDirectory 'tag-create-request.json'
    [ordered]@{ref=('refs/tags/'+$target.release.tag);sha=$workflowHead}|ConvertTo-Json|Set-Content -LiteralPath $tagRequest -Encoding utf8NoBOM
    Assert-AuditedMainBeforeMutation
    $report.tag_creation_attempted=$true
    $createdTagRaw=Invoke-ReleaseGh @('api','--method','POST','repos/astrynome-byte/Music/git/refs','--input',$tagRequest)
    $createdTag=$createdTagRaw|ConvertFrom-Json
    if($createdTag.ref-cne('refs/tags/'+$target.release.tag)-or$createdTag.object.type-cne'commit'-or$createdTag.object.sha-cne$workflowHead){throw 'New tag does not identify the exact workflow HEAD.'}
    $report.tag_created=$true
    $tagBeforeDraft=Get-ReleaseApi ('repos/astrynome-byte/Music/git/ref/tags/'+$encoded)
    if($tagBeforeDraft.object.type-cne'commit'-or$tagBeforeDraft.object.sha-cne$workflowHead){throw 'Owned tag changed before empty draft creation.'}
    $createRequest=Join-Path $OutputDirectory 'release-create-request.json'
    [ordered]@{tag_name=$target.release.tag;target_commitish=$workflowHead;name=$target.release.title;body=[IO.File]::ReadAllText($notes);draft=$true;prerelease=$true;generate_release_notes=$false}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $createRequest -Encoding utf8NoBOM
    Assert-AuditedMainBeforeMutation
    $report.draft_creation_attempted=$true
    $createdRaw=Invoke-ReleaseGh @('api','--method','POST','repos/astrynome-byte/Music/releases','--input',$createRequest)
    $created=$createdRaw|ConvertFrom-Json
    if(($created.id-isnot[long]-and$created.id-isnot[int])-or$created.id-le0){throw 'Create-release API did not return an owned release id.'}
    $createdId=$created.id;$report.release_id=$createdId;$report.draft_created=$true
    if($created.draft-isnot[bool]-or-not$created.draft-or$created.prerelease-isnot[bool]-or-not$created.prerelease-or$created.tag_name-cne$target.release.tag-or@($created.assets).Count-ne0){throw 'Created release is not the exact experimental draft.'}
    $emptyDraft=Get-ReleaseApi ('repos/astrynome-byte/Music/releases/'+$createdId)
    if($emptyDraft.id-ne$createdId-or$emptyDraft.draft-isnot[bool]-or-not$emptyDraft.draft-or$emptyDraft.prerelease-isnot[bool]-or-not$emptyDraft.prerelease-or$emptyDraft.tag_name-cne$target.release.tag-or@($emptyDraft.assets).Count-ne0){throw 'Owned empty private draft was not verified before any asset upload.'}
    foreach($asset in $validation.asset_receipts){
        $path=Join-Path $InputRoot $asset.member_path
        if((Get-Item $path).Length-ne$asset.bytes-or(Hash $path)-cne$asset.sha256){throw 'Approved asset changed before upload.'}
        $publicPath=Join-Path $OutputDirectory $asset.name
        [IO.File]::Copy($path,$publicPath,$false)
        Assert-AuditedMainBeforeMutation
        [void](Invoke-ReleaseGh @('release','upload',$target.release.tag,$publicPath,'--repo','astrynome-byte/Music'))
    }
    $uploaded=Get-ReleaseApi ('repos/astrynome-byte/Music/releases/'+$createdId)
    if($uploaded.id-ne$createdId-or-not$uploaded.draft-or-not$uploaded.prerelease-or@($uploaded.assets).Count-ne@($validation.asset_receipts).Count){throw 'Experimental draft does not contain exactly all approved assets.'}
    foreach($asset in $validation.asset_receipts){
        $matches=@($uploaded.assets|Where-Object{$_.name-ceq$asset.name})
        if($matches.Count-ne1-or$matches[0].size-ne$asset.bytes){throw 'Uploaded immutable asset name/size differs.'}
        $digest=$matches[0].PSObject.Properties['digest']
        if($digest-and$digest.Value-and$digest.Value-cne('sha256:'+$asset.sha256)){throw 'GitHub uploaded asset digest differs.'}
    }
    Assert-AuditedMainBeforeMutation
    $report.publication_attempted=$true
    [void](Invoke-ReleaseGh @('release','edit',$target.release.tag,'--repo','astrynome-byte/Music','--draft=false','--prerelease'))
    $report.published=$true
    $published=Get-ReleaseApi ('repos/astrynome-byte/Music/releases/'+$createdId)
    if($published.id-ne$createdId-or$published.draft-or-not$published.prerelease){throw 'Exact release was not published as experimental prerelease.'}
    $tagRef=Get-ReleaseApi ('repos/astrynome-byte/Music/git/ref/tags/'+$encoded)
    if($tagRef.object.type-cne'commit'-or$tagRef.object.sha-cne$workflowHead){throw 'Actual immutable published tag does not resolve to the audited workflow HEAD.'}
    $report.published=$true;$report.release_url=$published.html_url
    # This fresh client receives neither GH_TOKEN, credentials, cookies nor an
    # Authorization header. Signed CDN redirects are anonymous GitHub tickets.
    $handler=[Net.Http.HttpClientHandler]::new();$handler.UseDefaultCredentials=$false;$handler.PreAuthenticate=$false;$handler.Credentials=$null;$handler.DefaultProxyCredentials=$null;$handler.UseCookies=$false;$handler.AllowAutoRedirect=$true
    $client=[Net.Http.HttpClient]::new($handler);$client.Timeout=[TimeSpan]::FromMinutes(15);$client.DefaultRequestHeaders.Authorization=$null;$client.DefaultRequestHeaders.UserAgent.ParseAdd('Cadence-Public-Download-Verification/1.0')
    try{
        foreach($asset in $validation.asset_receipts){
            $remote=@($published.assets|Where-Object{$_.name-ceq$asset.name})
            if($remote.Count-ne1){throw 'Published asset missing.'}
            $url=[Uri]$remote[0].browser_download_url
            if($url.Scheme-cne'https'-or$url.Host-cne'github.com'-or-not$url.AbsolutePath.StartsWith('/astrynome-byte/Music/releases/download/',[StringComparison]::Ordinal)){throw 'GitHub API did not return the expected public release download URL.'}
            $download=Join-Path $OutputDirectory ('anonymous-'+$asset.name)
            $deadline=[Threading.CancellationTokenSource]::new([TimeSpan]::FromMinutes(15));$response=$null
            try{
                $response=$client.GetAsync($url,[Net.Http.HttpCompletionOption]::ResponseHeadersRead,$deadline.Token).GetAwaiter().GetResult()
                if(-not$response.IsSuccessStatusCode){throw ('Anonymous download failed: HTTP'+[int]$response.StatusCode)}
                $body=$response.Content.ReadAsStreamAsync().GetAwaiter().GetResult();$file=[IO.File]::Open($download,[IO.FileMode]::CreateNew)
                try{
                    $buffer=[byte[]]::new(65536);[long]$count=0
                    while(($read=$body.ReadAsync($buffer,0,$buffer.Length,$deadline.Token).GetAwaiter().GetResult())-gt0){$count+=$read;if($count-gt$asset.bytes){throw 'Anonymous response exceeded the exact approved asset byte length.'};$file.Write($buffer,0,$read)}
                }finally{$file.Dispose();$body.Dispose()}
                if((Get-Item $download).Length-ne$asset.bytes-or(Hash $download)-cne$asset.sha256){throw 'Anonymous actual downloaded asset bytes/SHA differ from the approved delivery.'}
                $report.assets += [ordered]@{kind=$asset.kind;name=$asset.name;url=$url.AbsoluteUri;bytes=$asset.bytes;sha256=$asset.sha256;anonymous_http_status=[int]$response.StatusCode;downloaded_without_account_or_Authorization=$true}
            }finally{if($response){$response.Dispose()};$deadline.Dispose()}
        }
    }finally{$client.Dispose();$handler.Dispose()}
    $installer=@($report.assets|Where-Object{$_.kind-ceq'msi'})[0]
    $guide=@($report.assets|Where-Object{$_.kind-ceq'guide'})[0]
    @("Voici une préversion expérimentale de Cadence Studio pour Windows64, encore en développement.",
      "Télécharger l'installateur : $($installer.url)","Guide français : $($guide.url)",
      "Version $($target.version). SHA-256 du MSI : $($installer.sha256)",
      "Double-clique sur le MSI puis suis l'assistant ; aucun outil de développement ni compte GitHub n'est nécessaire.",
      "Cette préversion a été testée automatiquement sur Windows Server2022CI ; Windows10/11 clients et écoutes restent à vérifier.",
      "Les fonctions payantes n'ont pas toutes un équivalent achevé. Cette livraison n'est pas le cadeau final. L'hébergement dépend de GitHub, sans permanence garantie.")|Set-Content (Join-Path $OutputDirectory 'MESSAGE-PARTAGE-FR.txt') -Encoding utf8
    $report.publicly_verified=$true;$report.status='experimental-prerelease-all-assets-anonymously-downloaded-and-sha256-verified'
}catch{
    $report.error=$_.Exception.Message
    # Only hide this invocation's own newly created release after a failed final
    # anonymous check; never delete an older release or move/delete any tag.
    if($createdId-and($report.published-or$report.publication_attempted)){
        try{$current=Get-ReleaseApi ('repos/astrynome-byte/Music/releases/'+$createdId);if($current.id-eq$createdId-and$current.tag_name-ceq$target.release.tag){Assert-AuditedMainBeforeMutation;[void](Invoke-ReleaseGh @('release','edit',$target.release.tag,'--repo','astrynome-byte/Music','--draft=true','--prerelease'));$report.withdrawn_after_failed_anonymous_verification=$true;$report.published=$false}}catch{$report.withdrawal_error=$_.Exception.Message}
    }
    # If no draft id was acquired, remove only this invocation's new tag and
    # only while its target and audited main still match. A retained private
    # draft keeps its tag for inspection; older tags/releases are untouched.
    if($report.draft_creation_attempted-and-not$createdId){$report.private_draft_outcome_unknown=$true;$report.tag_cleanup='retained-for-review-private-draft-outcome-unknown'}
    if($report.tag_creation_attempted-and-not$report.draft_creation_attempted-and-not$createdId-and-not$report.publication_attempted){
        try{
            $currentMain=Get-ReleaseApi 'repos/astrynome-byte/Music/commits/main'
            if($currentMain.sha-cne$target.android.main_commit){throw 'main changed; owned tag cleanup requires a new workflow audit.'}
            $ownedTag=Get-ReleaseApi ('repos/astrynome-byte/Music/git/ref/tags/'+$encoded) -AllowNotFound
            if($null-ne$ownedTag){
                if($ownedTag.ref-cne('refs/tags/'+$target.release.tag)-or$ownedTag.object.type-cne'commit'-or$ownedTag.object.sha-cne$workflowHead){throw 'Tag target changed; no tag deletion attempted.'}
                [void](Invoke-ReleaseGh @('api','--method','DELETE',('repos/astrynome-byte/Music/git/refs/tags/'+$encoded)))
                if($null-ne(Get-ReleaseApi ('repos/astrynome-byte/Music/git/ref/tags/'+$encoded) -AllowNotFound)){throw 'Owned temporary tag removal was not verified.'}
            }
            $report.tag_cleanup='owned-new-tag-absent-verified'
        }catch{$report.tag_cleanup=$_.Exception.Message}
    }
}finally{
    $report|ConvertTo-Json -Depth 12|Set-Content (Join-Path $OutputDirectory 'publication-report.json') -Encoding utf8
    Write-Host 'CADENCE_PUBLIC_DOWNLOAD_REPORT_BEGIN';Write-Host ($report|ConvertTo-Json -Depth 12 -Compress);Write-Host 'CADENCE_PUBLIC_DOWNLOAD_REPORT_END'
}
if(-not$report.publicly_verified){throw 'Public download delivery remains unvalidated; no usable anonymous link is claimed.'}
