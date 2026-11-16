# SPDX-License-Identifier: GPL-3.0-only
# Reused owned-window/capture/log helpers, definitions only; no process starts.
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
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr window,System.Text.StringBuilder value,int count);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr window);
 public static string Title(IntPtr window) { var b=new System.Text.StringBuilder(513);GetWindowText(window,b,513);return b.ToString(); }
 public static bool CloseOwned(IntPtr window,int expectedPid) {
  return Owned(window,expectedPid)&&PostMessage(window,0x0010,IntPtr.Zero,IntPtr.Zero);
 }
}
'@
function Capture-OwnedWindow([string] $Name, $Process, [string] $CaptureDirectory = $OutputDirectory, $CaptureReport = $report) {
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
            $path=Join-Path $CaptureDirectory $Name
            $bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)
            $CaptureReport.captures += [ordered]@{ status='saved_requires_visual_review';path=$path;sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant();pid=$Process.Id;method='desktop_pixels_cropped_to_owned_window' }
        } finally { $bitmap.Dispose() }
    } catch { $CaptureReport.captures += [ordered]@{ status='unavailable';error=$_.Exception.Message } }
}
function Save-CadenceApplicationLogEvidence([string] $CadenceDataRoot, [string] $EvidenceDirectory, [int] $OwnedPid) {
    # This exact profile was absent before this invocation. Never search another
    # profile or a score folder to obtain a missing diagnostic.
    $document=[ordered]@{schema_version=1;status='unavailable';owned_pid_context=$OwnedPid;source='fresh Cadence-only profile logs after owned process cleanup';file_pid_attribution_inferred=$false;files=@();notes=@();application_validation_inferred=$false}
    try {
        if(-not [IO.Path]::IsPathFullyQualified($CadenceDataRoot) -or [IO.Path]::GetFileName($CadenceDataRoot.TrimEnd('\','/')) -cne 'CadenceStudio') { throw 'Only the exact fresh Cadence data root is permitted.' }
        $applicationRoot=Join-Path $CadenceDataRoot 'CadenceStudio4'
        $logRoot=Join-Path $applicationRoot 'logs'
        foreach($directory in @($CadenceDataRoot,$applicationRoot,$logRoot)) {
            $item=Get-Item -LiteralPath $directory
            if(-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'The fresh Cadence log directory must be a plain directory.' }
        }
        $files=@(Get-ChildItem -LiteralPath $logRoot -File -Filter '*.log' |
            Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 4)
        foreach($file in $files) {
            $stream=[IO.File]::Open($file.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
            try {
                $length=$stream.Length
                [void]$stream.Seek([Math]::Max(0L,$length-16384L),[IO.SeekOrigin]::Begin)
                $bytes=[byte[]]::new([int][Math]::Min(16384L,$length))
                $count=0
                while($count -lt $bytes.Length) { $part=$stream.Read($bytes,$count,$bytes.Length-$count);if($part -eq 0){break};$count+=$part }
                if($count -eq 0){$tail=[byte[]]::new(0)}else{$tail=[byte[]]$bytes[0..($count-1)]}
            } finally { $stream.Dispose() }
            $document.files += [ordered]@{name=$file.Name;file_bytes=$length;tail_bytes=$count;tail_only=$length -gt $count;tail_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([byte[]]$tail)).ToLowerInvariant();text=[Text.Encoding]::UTF8.GetString([byte[]]$tail);last_write_utc=$file.LastWriteTimeUtc.ToString('o')}
        }
        $document.status=if($files.Count){'bounded_log_tails_collected'}else{'no_log_files_observed'}
    } catch { $document.notes += $_.Exception.Message }
    $document|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $EvidenceDirectory 'application-log-tails.json') -Encoding utf8
}

function Capture-OwnedImportDialog($Native,[string]$ExpectedTitle,$Process,[string]$Name,[string]$Directory,$Report) {
 $Process.Refresh();if($Process.HasExited){throw 'Owned application exited before its modal capture.'}
 $window=[IntPtr][long]$Native.dialog_handle
 if(-not[CadenceLibraryWindowNative]::Owned($window,$Process.Id)-or
    -not[CadenceLibraryWindowNative]::IsWindowVisible($window)-or-not[CadenceLibraryWindowNative]::IsWindowEnabled($window)-or
    [CadenceLibraryWindowNative]::Title($window)-cne$ExpectedTitle){throw 'The exact observed owned modal is no longer available.'}
 [void][CadenceLibraryWindowNative]::SetForegroundWindow($window)
 if([CadenceLibraryWindowNative]::GetForegroundWindow()-ne$window){throw 'Expected modal is not foreground; no screenshot of another window is taken.'}
 $rect=[CadenceLibraryWindowNative+Rect]::new()
 if(-not[CadenceLibraryWindowNative]::GetWindowRect($window,[ref]$rect)){throw 'Owned modal rectangle unavailable.'}
 $width=$rect.Right-$rect.Left;$height=$rect.Bottom-$rect.Top
 if($width-lt100-or$height-lt100-or([long]$width*$height)-gt12000000){throw 'Unexpected modal screenshot bounds.'}
 Add-Type -AssemblyName System.Drawing
 $bitmap=[Drawing.Bitmap]::new($width,$height)
 try {
  $graphics=[Drawing.Graphics]::FromImage($bitmap)
  try{$graphics.CopyFromScreen($rect.Left,$rect.Top,0,0,$bitmap.Size)}finally{$graphics.Dispose()}
  if(-not[CadenceLibraryWindowNative]::Owned($window,$Process.Id)-or[CadenceLibraryWindowNative]::Title($window)-cne$ExpectedTitle-or[CadenceLibraryWindowNative]::GetForegroundWindow()-ne$window){throw 'Observed modal changed during capture.'}
  $path=Join-Path $Directory $Name;$bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)
  $Report.captures+=,@{path=$path;pid=$Process.Id;title=$ExpectedTitle;bytes=(Get-Item $path).Length;sha256=(Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant();status='original_capture_requires_human_visual_review';method='desktop_pixels_cropped_only_to_verified_owned_modal'}
 }finally{$bitmap.Dispose()}
}
