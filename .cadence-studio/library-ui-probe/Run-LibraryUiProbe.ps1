# SPDX-License-Identifier: GPL-3.0-only
# Opens only the authenticated retained application on a disposable hosted runner.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $StagePath,
    [Parameter(Mandatory)][string] $ProbePath,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or
    $env:GITHUB_ACTIONS -ne 'true' -or $env:CI -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Library UI inspection is restricted to disposable hosted Windows x64 CI.'
}
if (-not $env:RUNNER_TEMP -or -not [Environment]::UserInteractive -or [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
    throw 'An interactive disposable runner desktop is required; no application was started.'
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$temporaryRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'OutputDirectory must be a new directory strictly below RUNNER_TEMP.'
}
$executable = [IO.Path]::GetFullPath((Join-Path $StagePath 'bin/CadenceStudio4.exe'))
$ProbePath = [IO.Path]::GetFullPath($ProbePath)
if (-not (Test-Path -LiteralPath $executable -PathType Leaf) -or -not (Test-Path -LiteralPath $ProbePath -PathType Leaf)) { throw 'Real retained executable and native probe are required.' }
$known = @('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if (@(Get-Process | Where-Object { $_.ProcessName -in $known }).Count) { throw 'A score application already exists. Nothing was started or closed.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$treeDirectory = Join-Path $OutputDirectory 'uia'
New-Item -ItemType Directory -Path $treeDirectory | Out-Null
$report = [ordered]@{
    schema_version = 1; status = 'pending'; scope = 'Owned PID UIA inspection and semantic navigation, never score editing'
    executable = $executable; executable_sha256 = (Get-FileHash $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    probe = $ProbePath; probe_sha256 = (Get-FileHash $ProbePath -Algorithm SHA256).Hash.ToLowerInvariant()
    started_utc = [DateTime]::UtcNow.ToString('o'); pid = $null; probe_exit_code = $null
    profile_isolated_by_script = $false; hosted_disposable_profile = $true
    action_policy = 'Only Introduction owned modal may close before navigation; only exact Home/Scores/Local library semantic names may invoke'
    captures = @(); cleanup = [ordered]@{ forced = $false; exit_code = $null; events = @(); error = $null }
    library_content_observed = $false; score_editing_tested = $false; favorites_tested = $false
    probe_cleanup_forced = $false
    error = $null
}
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class CadenceLibraryWindowNative {
 public delegate bool Callback(IntPtr window,IntPtr state);
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] static extern bool EnumWindows(Callback cb,IntPtr state);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window,out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window,out Rect rect);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
 [DllImport("user32.dll",SetLastError=true)] static extern bool PostMessage(IntPtr window,uint msg,IntPtr w,IntPtr l);
 public static bool Owned(IntPtr window,int expectedPid) { uint pid;return window!=IntPtr.Zero&&GetWindowThreadProcessId(window,out pid)!=0&&pid==(uint)expectedPid; }
 public static IntPtr[] Windows(int expectedPid) {
  var list=new List<IntPtr>();EnumWindows((w,s)=>{if(Owned(w,expectedPid)&&IsWindowVisible(w))list.Add(w);return true;},IntPtr.Zero);return list.ToArray();
 }
 public static bool CloseOwned(IntPtr window,int expectedPid) {
  return Owned(window,expectedPid)&&PostMessage(window,0x0010,IntPtr.Zero,IntPtr.Zero);
 }
}
'@
function Capture-OwnedWindow([string] $Name, $Process) {
    try {
        $Process.Refresh()
        if ($Process.HasExited) { throw 'Owned process has exited.' }
        $best = [IntPtr]::Zero; [long]$area = 0
        foreach ($window in @([CadenceLibraryWindowNative]::Windows($Process.Id))) {
            $rect = [CadenceLibraryWindowNative+Rect]::new()
            if ([CadenceLibraryWindowNative]::GetWindowRect($window,[ref]$rect)) {
                [long]$candidate = ([long]$rect.Right-$rect.Left)*([long]$rect.Bottom-$rect.Top)
                if ($candidate -gt $area) { $area=$candidate;$best=$window }
            }
        }
        if ($best -eq [IntPtr]::Zero -or $area -gt 12000000 -or -not [CadenceLibraryWindowNative]::Owned($best,$Process.Id)) { throw 'No bounded owned capture window.' }
        [void][CadenceLibraryWindowNative]::SetForegroundWindow($best)
        $rect = [CadenceLibraryWindowNative+Rect]::new()
        if (-not [CadenceLibraryWindowNative]::Owned($best,$Process.Id) -or -not [CadenceLibraryWindowNative]::GetWindowRect($best,[ref]$rect)) { throw 'Owned rectangle unavailable.' }
        Add-Type -AssemblyName System.Drawing
        $bitmap = [Drawing.Bitmap]::new(($rect.Right-$rect.Left),($rect.Bottom-$rect.Top))
        try {
            $graphics=[Drawing.Graphics]::FromImage($bitmap)
            try { $graphics.CopyFromScreen($rect.Left,$rect.Top,0,0,$bitmap.Size) } finally { $graphics.Dispose() }
            $path=Join-Path $OutputDirectory $Name
            $bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)
            $report.captures += [ordered]@{ status='saved_requires_visual_review';path=$path;sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant();pid=$Process.Id;method='desktop_pixels_cropped_to_owned_window' }
        } finally { $bitmap.Dispose() }
    } catch { $report.captures += [ordered]@{ status='unavailable';error=$_.Exception.Message } }
}
$app = $null; $probe = $null; $stdout = $null; $stderr = $null
try {
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$executable;$start.WorkingDirectory=Split-Path -Parent $executable
    $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    foreach ($arg in @('--test-mode','--session-type','start-empty')) { $start.ArgumentList.Add($arg) }
    $start.Environment['PATH']=(Split-Path -Parent $executable)+';'+(Join-Path $env:SystemRoot 'System32')
    foreach ($key in @($start.Environment.Keys)) {
        if ($key -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|ExtensionSdkDir$|FrameworkDir|FrameworkVersion)') { [void]$start.Environment.Remove($key) }
    }
    $start.Environment['QT_ACCESSIBILITY']='1'
    $app=[Diagnostics.Process]::new();$app.StartInfo=$start
    if (-not $app.Start()) { throw 'Application process did not start.' }
    $report.pid=$app.Id;$stdout=$app.StandardOutput.ReadToEndAsync();$stderr=$app.StandardError.ReadToEndAsync()
    $clock=[Diagnostics.Stopwatch]::StartNew()
    while ($clock.Elapsed.TotalSeconds -lt 35) {
        $app.Refresh();if ($app.HasExited) { throw 'Application exited before inspection.' }
        if (@([CadenceLibraryWindowNative]::Windows($app.Id)).Count) { break }
        Start-Sleep -Milliseconds 200
    }
    Capture-OwnedWindow 'before-navigation.png' $app
    $probeStart=[Diagnostics.ProcessStartInfo]::new();$probeStart.FileName=$ProbePath;$probeStart.UseShellExecute=$false
    $probeStart.RedirectStandardOutput=$true;$probeStart.RedirectStandardError=$true
    foreach ($arg in @('--pid',[string]$app.Id,'--output',$treeDirectory)) { $probeStart.ArgumentList.Add($arg) }
    $probe=[Diagnostics.Process]::new();$probe.StartInfo=$probeStart
    if (-not $probe.Start()) { throw 'Native UIA inspector did not start.' }
    $probeOut=$probe.StandardOutput.ReadToEndAsync();$probeErr=$probe.StandardError.ReadToEndAsync()
    if (-not $probe.WaitForExit(90000)) { $probe.Kill($true);$probe.WaitForExit();throw 'UIA inspector timed out; only its owned process tree was stopped.' }
    $report.probe_exit_code=$probe.ExitCode
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stdout.log'),$probeOut.GetAwaiter().GetResult())
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stderr.log'),$probeErr.GetAwaiter().GetResult())
    $uiaPath=Join-Path $treeDirectory 'uia-report.json'
    if (-not (Test-Path -LiteralPath $uiaPath)) { throw 'Native inspector returned no UIA report; no UI validation inferred.' }
    $uia=Get-Content -LiteralPath $uiaPath -Raw | ConvertFrom-Json
    if ($uia.pid -ne $app.Id) { throw 'Inspector reported a different process.' }
    $report.library_content_observed=$uia.library_content_observed
    $report.status=$uia.status
    Capture-OwnedWindow 'after-navigation.png' $app
    if ($probe.ExitCode -notin @(0,2)) { throw "UIA inspector failed: $($probe.ExitCode)" }
} catch { $report.status='probe_failed';$report.error=$_.Exception.Message }
finally {
    if ($null -ne $probe) {
        try {
            $probe.Refresh()
            if (-not $probe.HasExited) { $report.probe_cleanup_forced=$true;$probe.Kill($true);[void]$probe.WaitForExit(5000) }
        } catch { if (-not $report.error) { $report.error=$_.Exception.Message } }
        finally { $probe.Dispose() }
    }
    if ($null -ne $app) {
        try {
            $closeClock=[Diagnostics.Stopwatch]::StartNew()
            while ($closeClock.Elapsed.TotalSeconds -lt 12) {
                $app.Refresh();if ($app.HasExited) { break }
                foreach ($window in @([CadenceLibraryWindowNative]::Windows($app.Id))) {
                    $app.Refresh();if ($app.HasExited) { break }
                    $posted=[CadenceLibraryWindowNative]::CloseOwned($window,$app.Id)
                    $report.cleanup.events += [ordered]@{ action='cleanup_wm_close_owned_window';pid=$app.Id;handle=$window.ToInt64();posted=$posted }
                }
                if ($app.WaitForExit(250)) { break }
            }
            $app.Refresh()
            if (-not $app.HasExited) { $report.cleanup.forced=$true;$app.Kill($true);if (-not $app.WaitForExit(5000)) { throw 'Owned application could not be stopped.' } }
            $report.cleanup.exit_code=$app.ExitCode
            [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stdout.log'),$stdout.GetAwaiter().GetResult())
            [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stderr.log'),$stderr.GetAwaiter().GetResult())
        } catch { $report.cleanup.error=$_.Exception.Message }
        finally { $app.Dispose() }
    }
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'library-ui-report.json') -Encoding utf8
}
if ($report.error -or $report.cleanup.error -or $report.cleanup.forced) { throw 'Owned library inspection or cleanup failed; inspect retained reports.' }
if (-not $report.library_content_observed) { Write-Warning "Library UI remains blocked/unvalidated: $($report.status). Tree and screenshots are evidence, not a pass."; exit 2 }
else { Write-Host 'Observed active library tab and its Add control through UIA. No files were added or changed.' }
