# SPDX-License-Identifier: GPL-3.0-only
# Read-only Home/Intro readiness, owned capture and ordinary owned-window close.
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string] $Executable,
 [Parameter(Mandatory)][string] $OutputDirectory,
 [string] $NativeProbePath = (Join-Path $env:RUNNER_TEMP 'combined-ui-probe/UiReadyProbe.exe')
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or -not [Environment]::UserInteractive -or [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) { throw 'Use a disposable interactive hosted Windows x64 runner.' }
$Executable=[IO.Path]::GetFullPath($Executable)
$OutputDirectory=[IO.Path]::GetFullPath($OutputDirectory)
$NativeProbePath=[IO.Path]::GetFullPath($NativeProbePath)
$temporary=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
if (-not $OutputDirectory.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $OutputDirectory)) { throw 'Use a new output below RUNNER_TEMP.' }
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf) -or -not (Test-Path -LiteralPath $NativeProbePath -PathType Leaf)) { throw 'Authenticated app and compiled read-only SDK probe required.' }
if ((Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash.ToLowerInvariant() -ne '35d8b076cacddb8b37a4f23aeea9899e6ab4ac9214e9a5b1125bbeccf26cf39e') { throw 'Expected unchanged full-build2002 executable.' }
$known=@('CadenceStudio4','CadenceStudio4Development','MuseScore4','MuseScore4Development','MuseScoreStudio4')
if (@(Get-Process | Where-Object { $_.ProcessName -in $known }).Count) { throw 'Existing score application: nothing started or closed.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$treeDirectory=Join-Path $OutputDirectory 'readiness'
New-Item -ItemType Directory -Path $treeDirectory | Out-Null
$report=[ordered]@{
 schema_version=1;status='failed';exit_status=1;executable=$Executable;executable_sha256=(Get-FileHash $Executable -Algorithm SHA256).Hash.ToLowerInvariant()
 scope='Read-only actual Home/Intro readiness, capture and clean owned close; no editing, library interaction or listening'
 native_probe=$NativeProbePath;native_probe_sha256=(Get-FileHash $NativeProbePath -Algorithm SHA256).Hash.ToLowerInvariant();pid=$null
 startup=[ordered]@{status='pending';semantic_readiness=$null};shutdown=[ordered]@{status='pending';exit_code=$null;forced=$false;events=@();error=$null}
 captures=@();visual_review_completed=$false;profile_seeded_or_reset_by_script=$false;probe_forced=$false;error=$null
}
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class CadenceReadyWindowNative {
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
        foreach ($window in @([CadenceReadyWindowNative]::Windows($Process.Id))) {
            $rect = [CadenceReadyWindowNative+Rect]::new()
            if ([CadenceReadyWindowNative]::GetWindowRect($window,[ref]$rect)) {
                [long]$candidate = ([long]$rect.Right-$rect.Left)*([long]$rect.Bottom-$rect.Top)
                if ($candidate -gt $area) { $area=$candidate;$best=$window }
            }
        }
        if ($best -eq [IntPtr]::Zero -or $area -gt 12000000 -or -not [CadenceReadyWindowNative]::Owned($best,$Process.Id)) { throw 'No bounded owned capture window.' }
        [void][CadenceReadyWindowNative]::SetForegroundWindow($best)
        $rect = [CadenceReadyWindowNative+Rect]::new()
        if (-not [CadenceReadyWindowNative]::Owned($best,$Process.Id) -or -not [CadenceReadyWindowNative]::GetWindowRect($best,[ref]$rect)) { throw 'Owned rectangle unavailable.' }
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
$app=$null;$probe=$null;$stdout=$null;$stderr=$null
try {
 $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Executable;$start.WorkingDirectory=Split-Path -Parent $Executable
 $start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
 foreach($arg in @('--test-mode','--session-type','start-empty')){$start.ArgumentList.Add($arg)}
 $start.Environment['PATH']=(Split-Path -Parent $Executable)+';'+(Join-Path $env:SystemRoot 'System32')
 foreach($name in @($start.Environment.Keys)){if($name -match '^(?i:QT|QML|CMAKE_|VCPKG_|VSCMD_|VSINSTALLDIR$|VCINSTALLDIR$|VCTools|INCLUDE$|LIB$|LIBPATH$|WindowsSdk|WindowsSDK|UniversalCRTSdkDir$|UCRTVersion$|DevEnvDir$|FrameworkDir|FrameworkVersion)'){[void]$start.Environment.Remove($name)}}
 $start.Environment['QT_ACCESSIBILITY']='1'
 $app=[Diagnostics.Process]::new();$app.StartInfo=$start
 if(-not $app.Start()){throw 'Retained application did not start.'}
 $report.pid=$app.Id;$stdout=$app.StandardOutput.ReadToEndAsync();$stderr=$app.StandardError.ReadToEndAsync()
 $probeStart=[Diagnostics.ProcessStartInfo]::new();$probeStart.FileName=$NativeProbePath;$probeStart.UseShellExecute=$false
 $probeStart.RedirectStandardOutput=$true;$probeStart.RedirectStandardError=$true
 foreach($arg in @('--pid',[string]$app.Id,'--output',$treeDirectory)){$probeStart.ArgumentList.Add($arg)}
 $probe=[Diagnostics.Process]::new();$probe.StartInfo=$probeStart
 if(-not $probe.Start()){throw 'Read-only readiness probe did not start.'}
 $probeOut=$probe.StandardOutput.ReadToEndAsync();$probeErr=$probe.StandardError.ReadToEndAsync()
 if(-not $probe.WaitForExit(60000)){$probe.Kill($true);[void]$probe.WaitForExit(5000);$report.probe_forced=$true;throw 'Read-only readiness probe timed out.'}
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stdout.log'),$probeOut.GetAwaiter().GetResult())
 [IO.File]::WriteAllText((Join-Path $OutputDirectory 'probe.stderr.log'),$probeErr.GetAwaiter().GetResult())
 $readiness=Get-Content -LiteralPath (Join-Path $treeDirectory 'native-readiness.json') -Raw | ConvertFrom-Json
 $report.startup.semantic_readiness=$readiness
 if($probe.ExitCode -ne 0 -or $readiness.pid -ne $app.Id -or -not $readiness.ready -or $readiness.status -notin @('ready_owned_semantic_control','ready_owned_introduction_dialog')){throw 'Actual Home/Intro not proven; splash alone never passes.'}
 $app.Refresh();if($app.HasExited){throw 'App exited before actual-window capture.'}
 $report.startup.status='visible_window_responding_observed'
 Capture-OwnedWindow 'actual-home-or-intro.png' $app
 if(@($report.captures | Where-Object {$_.status -eq 'saved_requires_visual_review'}).Count -ne 1){throw 'Owned window screenshot required for later visual inspection.'}
} catch {$report.error=$_.Exception.Message;if($null -ne $app){try{Capture-OwnedWindow 'blocked-window-for-diagnosis.png' $app}catch{}}}
finally {
 if($null -ne $probe){try{$probe.Refresh();if(-not $probe.HasExited){$report.probe_forced=$true;$probe.Kill($true);[void]$probe.WaitForExit(5000)}}catch{if(-not $report.error){$report.error=$_.Exception.Message}}finally{$probe.Dispose()}}
 if($null -ne $app){
  try {
   $clock=[Diagnostics.Stopwatch]::StartNew()
   while($clock.Elapsed.TotalSeconds -lt 15){
    $app.Refresh();if($app.HasExited){break}
    foreach($window in @([CadenceReadyWindowNative]::Windows($app.Id))){
     $app.Refresh();if($app.HasExited){break}
     $posted=[CadenceReadyWindowNative]::CloseOwned($window,$app.Id)
     $report.shutdown.events += [ordered]@{action='wm_close_owned_window';pid=$app.Id;handle=$window.ToInt64();posted=$posted}
    }
    if($app.WaitForExit(250)){break}
   }
   $app.Refresh();if(-not $app.HasExited){$report.shutdown.forced=$true;$app.Kill($true);if(-not $app.WaitForExit(5000)){throw 'Owned application could not be stopped.'}}
   $report.shutdown.exit_code=$app.ExitCode
   $report.shutdown.status=if($report.shutdown.forced){'forced_cleanup_not_pass'}else{'closed_after_owned_window_close'}
   [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stdout.log'),$stdout.GetAwaiter().GetResult())
   [IO.File]::WriteAllText((Join-Path $OutputDirectory 'application.stderr.log'),$stderr.GetAwaiter().GetResult())
  }catch{$report.shutdown.error=$_.Exception.Message}finally{$app.Dispose()}
 }
 if(-not $report.error -and -not $report.shutdown.error -and -not $report.shutdown.forced -and -not $report.probe_forced -and $report.shutdown.exit_code -eq 0 -and $report.startup.status -eq 'visible_window_responding_observed'){$report.status='startup_observed_closed_cleanly';$report.exit_status=0}
 $report | ConvertTo-Json -Depth 18 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'gui-report.json') -Encoding utf8
 Write-Host 'CADENCE_COMBINED_GUI_REPORT_BEGIN';$report | ConvertTo-Json -Depth 18 -Compress | Write-Host;Write-Host 'CADENCE_COMBINED_GUI_REPORT_END'
}
if($report.exit_status -ne 0){throw "Actual Home/Intro observation failed: $($report.error) cleanup:$($report.shutdown.error)"}
