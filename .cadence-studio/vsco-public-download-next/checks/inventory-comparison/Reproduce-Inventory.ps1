# Data-only: evaluate exact function ASTs, with GET stubbed from the real audit.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Publisher,[Parameter(Mandatory)][string]$Audit,[Parameter(Mandatory)][string]$Target,[Parameter(Mandatory)][string]$Output)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Publisher,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Publisher syntax errors.'}
foreach($name in @('Get-WorkflowInventory','Assert-WorkflowInventory')){
    $functions=@($ast.FindAll({param($n)$n-is[Management.Automation.Language.FunctionDefinitionAst]-and$n.Name-ceq$name},$true))
    if($functions.Count-ne1){throw ('Exact function required: '+$name)}
    . ([scriptblock]::Create($functions[0].Extent.Text))
}
$script:auditData=Get-Content -LiteralPath $Audit -Raw -Encoding utf8|ConvertFrom-Json
$targetData=Get-Content -LiteralPath $Target -Raw -Encoding utf8|ConvertFrom-Json
function Get-ReleaseApi([string]$Endpoint){
    # These GET responses are projections of authenticated, reviewed workflow
    # records. No API or publisher entry point is called by this data check.
    foreach($scope in @('main','head')){
        $commit=if($scope-ceq'main'){$script:auditData.main_commit}else{$script:auditData.head_commit}
        $treeId=if($scope-ceq'main'){'0'*40}else{'1'*40}
        if($Endpoint-ceq('repos/astrynome-byte/Music/commits/'+$commit)){
            return [pscustomobject]@{sha=$commit;commit=[pscustomobject]@{tree=[pscustomobject]@{sha=$treeId}}}
        }
        if($Endpoint-ceq('repos/astrynome-byte/Music/git/trees/'+$treeId+'?recursive=1')){
            return [pscustomobject]@{truncated=$false;tree=@($script:auditData.workflows|Where-Object scope -CEQ $scope|ForEach-Object{[pscustomobject]@{type='blob';path=$_.path;sha=$_.blob_sha1}})}
        }
    }
    throw 'Unexpected GET in data-only inventory reproduction.'
}
$records=@()
foreach($scope in @('main','head')){
    $commit=if($scope-ceq'main'){$auditData.main_commit}else{$auditData.head_commit}
    $expected=if($scope-ceq'main'){$targetData.android.main_workflows}else{$targetData.android.tag_workflows}
    $actual=@(Get-WorkflowInventory $commit)
    $accepted=$false;$failure=$null
    try{Assert-WorkflowInventory $actual $expected;$accepted=$true}catch{$failure=$_.Exception.Message}
    $a=@($actual|Sort-Object path);$e=@($expected|Sort-Object path)
    $mismatches=@(for($i=0;$i-lt[Math]::Min($a.Count,$e.Count);$i++){
        if($a[$i].path-cne$e[$i].path-or$a[$i].blob_sha1-cne$e[$i].blob_sha1){[ordered]@{index=$i;actual_path=$a[$i].path;expected_path=$e[$i].path;actual_type=$a[$i].GetType().FullName;expected_type=$e[$i].GetType().FullName}}
    })
    $records += [ordered]@{scope=$scope;actual_count=$actual.Count;expected_count=@($expected).Count;accepted=$accepted;error=$failure;legacy_sorted_first_mismatches=@($mismatches|Select-Object -First 5)}
}
[ordered]@{schema_version=1;scope='Exact publisher AST functions; real 54+1 reviewed records; GET stub only';publisher_sha256=(Get-FileHash -LiteralPath $Publisher -Algorithm SHA256).Hash.ToLowerInvariant();audit_sha256=(Get-FileHash -LiteralPath $Audit -Algorithm SHA256).Hash.ToLowerInvariant();target_sha256=(Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant();culture=[Globalization.CultureInfo]::CurrentCulture.Name;records=$records;network_executed=$false;publication_executed=$false}|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $Output -Encoding utf8NoBOM
Write-Output ('Data-only exact-function results: '+(($records|ForEach-Object{$_.scope+':'+$_.accepted})-join', '))
