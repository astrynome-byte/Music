# Exact fixed function AST; reviewed real records; no publisher/network execution.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Publisher,[Parameter(Mandatory)][string]$Target,[Parameter(Mandatory)][string]$Output)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Publisher,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Publisher syntax errors.'}
$fn=@($ast.FindAll({param($n)$n-is[Management.Automation.Language.FunctionDefinitionAst]-and$n.Name-ceq'Assert-WorkflowInventory'},$true))
if($fn.Count-ne1){throw 'One exact comparator function required.'}
. ([scriptblock]::Create($fn[0].Extent.Text))
$targetData=Get-Content -LiteralPath $Target -Raw -Encoding utf8|ConvertFrom-Json
$expected=@($targetData.android.tag_workflows)
if($expected.Count-ne54){throw 'This check must use the real reviewed 54-record snapshot.'}
$records=[Collections.Generic.List[object]]::new()
function Real-Actual {
    $items=@($expected|ForEach-Object{[ordered]@{path=$_.path;blob_sha1=$_.blob_sha1}})
    [Array]::Reverse($items)
    return $items
}
function Check([string]$Name,$Actual,$Reviewed,[bool]$Accept){
    $accepted=$false;$message=$null
    try{Assert-WorkflowInventory $Actual $Reviewed;$accepted=$true}catch{$message=$_.Exception.Message}
    $records.Add([ordered]@{name=$Name;accepted=$accepted;expected_accept=$Accept;error=$message})
    if($accepted-ne$Accept){throw ('Unexpected comparator result: '+$Name+'; '+$message)}
}
$originalCulture=[Globalization.CultureInfo]::CurrentCulture
try{
    foreach($culture in @('en-US','fr-FR','tr-TR')){
        [Globalization.CultureInfo]::CurrentCulture=[Globalization.CultureInfo]::GetCultureInfo($culture)
        Check ('real54-reversed-ordered-vs-pscustom-'+$culture) (Real-Actual) $expected $true
    }
    $a=Real-Actual;$a[0]=[pscustomobject]@{path=$a[0].path;blob_sha1=$a[0].blob_sha1};Check 'real54-mixed-object-types' $a $expected $true
    $a=Real-Actual;$a[0].blob_sha1=('a'*40);Check 'changed-valid-blob' $a $expected $false
    $a=Real-Actual;$a[0].path='.github/workflows/unreviewed.yml';Check 'same-count-renamed-path' $a $expected $false
    $a=Real-Actual;Check 'removed-record' @($a|Select-Object -Skip 1) $expected $false
    $a=Real-Actual;Check 'added-record' @($a+[ordered]@{path='.github/workflows/unreviewed.yml';blob_sha1=('a'*40)}) $expected $false
    $a=Real-Actual;$a[0].path=$a[1].path;Check 'duplicate-actual-path' $a $expected $false
    $e=@($expected|ForEach-Object{[pscustomobject]@{path=$_.path;blob_sha1=$_.blob_sha1}});$e[0].path=$e[1].path;Check 'duplicate-reviewed-path' (Real-Actual) $e $false
    $a=Real-Actual;$a[0].path=$a[0].path.ToUpperInvariant();Check 'case-only-path-change' $a $expected $false
    $a=Real-Actual;$a[0].blob_sha1=$true;Check 'boolean-blob' $a $expected $false
    $a=Real-Actual;$a[0].blob_sha1=('A'*40);Check 'uppercase-invalid-blob' $a $expected $false
    $a=Real-Actual;$a[0].path='../escape.yml';Check 'invalid-path' $a $expected $false
    $a=Real-Actual;$a[0]=[ordered]@{path=$a[0].path};Check 'missing-blob-field' $a $expected $false
    $a=Real-Actual;$a[0]='not-a-workflow-record';Check 'string-record' $a $expected $false
    Check 'empty-inventory' @() @() $false
    $a=Real-Actual;Check 'over-bound-inventory' @($a+$a+$a) @($a+$a+$a) $false
    [ordered]@{schema_version=1;scope='Exact comparator AST; bounded real54 data cases only';checks=$records.Count;records=$records;network_executed=$false;publication_executed=$false}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Output -Encoding utf8NoBOM
    Write-Output ('PASS '+$records.Count+' exact-function ordinal inventory data checks; no network/publication.')
}finally{[Globalization.CultureInfo]::CurrentCulture=$originalCulture}
