# SPDX-License-Identifier: GPL-3.0-only
# Dedicated Windows test accounts/VMs only. Does not reset or isolate a profile.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Executable,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [ValidateRange(5, 45)][int] $StartupTimeoutSeconds = 35,
    [ValidateRange(1, 10)][int] $StableWindowSeconds = 3,
    [ValidateRange(1, 15)][int] $CloseTimeoutSeconds = 10,
    [switch] $CaptureDesktopFallback
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$artifactRoot = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $artifactRoot) { throw 'OutputDirectory must be new; existing results are never replaced.' }
New-Item -ItemType Directory -Path $artifactRoot | Out-Null
$started = [DateTime]::UtcNow
$report = [ordered]@{
    schema_version = 1
    scope = 'GUI process startup/window responsiveness and controlled shutdown only'
    started_utc = $started.ToString('o')
    executable = $Executable
    executable_sha256 = $null
    arguments = @('--test-mode', '--session-type', 'start-empty')
    platform = [Environment]::OSVersion.ToString()
    interactive_session = [Environment]::UserInteractive
    session_id = $null
    profile_isolated_by_script = $false
    first_launch_profile_verified = $false
    no_score_argument = $true
    startup_timeout_seconds = $StartupTimeoutSeconds
    stable_window_seconds = $StableWindowSeconds
    status = 'pending'
    startup = [ordered]@{ status = 'not_started'; pid = $null; elapsed_seconds = $null; exit_code = $null; observation = $null }
    observations = @()
    capture = [ordered]@{ status = 'not_attempted'; method = $null; path = $null; error = $null }
    shutdown = [ordered]@{ status = 'not_started'; close_requested = $false; owned_window_close_requested = $false; forced = $false; exit_code = $null; close_error = $null; error = $null; elapsed_seconds = $null; events = @() }
    limitations = @(
        'A visible responsive window may be a setup/welcome/recovery dialog; screenshots require inspection.',
        'This does not validate installation, editing, notation content, audio, accessibility or a human first-launch workflow.',
        'The application can write settings in its current Windows profile. Use a disposable test account or VM.',
        'No factory reset, profile deletion, score opening, keystroke injection or dialog acceptance is performed.'
    )
}
$appProcess = $null
$windowHandle = [IntPtr]::Zero
$startupObserved = $false
$exitStatus = 1

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        $report.status = 'blocked_not_windows'
        $exitStatus = 2
    } else {
        $report.session_id = [Diagnostics.Process]::GetCurrentProcess().SessionId
        $candidate = [IO.Path]::GetFullPath($Executable)
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf) -or [IO.Path]::GetExtension($candidate) -ine '.exe') {
            throw 'Executable must be the real staged Windows .exe, not an AppRun or launcher script.'
        }
        $report.executable = $candidate
        $report.executable_sha256 = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        $knownNames = @([IO.Path]::GetFileNameWithoutExtension($candidate), 'MuseScore4', 'MuseScore4Development', 'MuseScoreStudio4', 'CadenceStudio4', 'CadenceStudio4Development') | Select-Object -Unique
        $existing = @(Get-Process | Where-Object { $_.ProcessName -in $knownNames } | Select-Object Id, ProcessName)
        if ($existing.Count) {
            $report.status = 'blocked_existing_score_application'
            $report['existing_processes'] = $existing
            $exitStatus = 2
        } elseif (-not [Environment]::UserInteractive -or $report.session_id -eq 0) {
            $report.status = 'blocked_no_interactive_desktop'
            $exitStatus = 2
        } elseif ($env:QT_QPA_PLATFORM -match '^(offscreen|minimal|vnc)' -or $env:MU_QT_QPA_PLATFORM -match '^(offscreen|minimal|vnc)') {
            $report.status = 'blocked_offscreen_qt_platform'
            $exitStatus = 2
        } else {
            if (-not ('CadenceGuiProbeNativeV1' -as [type])) {
                Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
public static class CadenceGuiProbeNativeV1 {
    public delegate bool EnumWindowsProc(IntPtr window, IntPtr state);
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    public sealed class WindowInfo {
        public long Handle; public string Title; public string ClassName;
        public long OwnerHandle; public int Left, Top, Width, Height; public bool Visible, Enabled;
    }
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc callback, IntPtr state);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr window);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr window, uint command);
    [DllImport("user32.dll", SetLastError=true)] static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out Rect rect);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr window, StringBuilder text, int length);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr window, StringBuilder text, int length);
    [DllImport("user32.dll", SetLastError=true)] static extern IntPtr SendMessageTimeout(IntPtr window, uint message, IntPtr wParam, IntPtr lParam, uint flags, uint milliseconds, out IntPtr result);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
    public static WindowInfo[] WindowsForProcess(int processId) {
        var windows = new List<WindowInfo>();
        EnumWindows((window, state) => {
            uint pid; GetWindowThreadProcessId(window, out pid);
            if (pid != (uint)processId || !IsWindowVisible(window)) return true;
            Rect rect; if (!GetWindowRect(window, out rect)) return true;
            var text = new StringBuilder(4096); GetWindowText(window, text, text.Capacity);
            var type = new StringBuilder(512); GetClassName(window, type, type.Capacity);
            windows.Add(new WindowInfo { Handle=window.ToInt64(), Title=text.ToString(), ClassName=type.ToString(),
                OwnerHandle=GetWindow(window, 4).ToInt64(), Enabled=IsWindowEnabled(window),
                Left=rect.Left, Top=rect.Top, Width=rect.Right-rect.Left, Height=rect.Bottom-rect.Top, Visible=true });
            return true;
        }, IntPtr.Zero);
        return windows.ToArray();
    }
    public static bool PingWindow(IntPtr window, uint timeoutMilliseconds) {
        IntPtr ignored;
        return SendMessageTimeout(window, 0, IntPtr.Zero, IntPtr.Zero, 2, timeoutMilliseconds, out ignored) != IntPtr.Zero;
    }
    public static bool IsOwnedWindow(IntPtr window, int expectedPid) {
        uint actualPid;
        return window != IntPtr.Zero && GetWindowThreadProcessId(window, out actualPid) != 0 && actualPid == (uint)expectedPid;
    }
    public static bool PostCloseOwnedWindow(IntPtr window, int expectedPid, out int error) {
        error = 0;
        // Check immediately before the only posted action. Never target another PID.
        if (!IsOwnedWindow(window, expectedPid)) { error = -1; return false; }
        bool posted = PostMessage(window, 0x0010, IntPtr.Zero, IntPtr.Zero); // WM_CLOSE, never dialog acceptance.
        if (!posted) error = Marshal.GetLastWin32Error();
        return posted;
    }
    // Process.Responding is checked in a bounded task rather than blocking the probe indefinitely.
    public static Task<bool> BeginProcessResponding(int pid) {
        return Task.Run(() => { using (var process = Process.GetProcessById(pid)) { return process.Responding; } });
    }
}
'@
            }
            $appProcess = Start-Process -FilePath $candidate -ArgumentList $report.arguments `
                -WorkingDirectory ([IO.Path]::GetDirectoryName($candidate)) -PassThru `
                -RedirectStandardOutput (Join-Path $artifactRoot 'stdout.log') `
                -RedirectStandardError (Join-Path $artifactRoot 'stderr.log')
            $report.startup.pid = $appProcess.Id
            $report.startup.status = 'waiting_for_visible_responsive_window'
            $clock = [Diagnostics.Stopwatch]::StartNew()
            $stableSince = $null
            $stableHandle = [long]0
            $lastRecorded = -1
            $respondingTask = $null
            while ($clock.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds) {
                $appProcess.Refresh()
                if ($appProcess.HasExited) {
                    $report.startup.status = 'exited_before_stable_window'
                    $report.startup.exit_code = $appProcess.ExitCode
                    break
                }
                $remainingMs = [int](1000 * ($StartupTimeoutSeconds - $clock.Elapsed.TotalSeconds))
                if ($remainingMs -le 0) { break }
                $main = $appProcess.MainWindowHandle.ToInt64()
                $windows = @([CadenceGuiProbeNativeV1]::WindowsForProcess($appProcess.Id) | Where-Object { $_.Width -ge 320 -and $_.Height -ge 200 })
                $selected = $windows | Sort-Object @{Expression = { $_.Handle -eq $main }; Descending = $true}, @{Expression = { [long]$_.Width * $_.Height }; Descending = $true} | Select-Object -First 1
                $processResponding = $false
                $messageResponding = $false
                if ($null -ne $selected) {
                    $windowHandle = [IntPtr]::new($selected.Handle)
                    $messageResponding = [CadenceGuiProbeNativeV1]::PingWindow($windowHandle, [uint32][Math]::Min(250, $remainingMs))
                    if ($messageResponding) {
                        if ($null -eq $respondingTask) { $respondingTask = [CadenceGuiProbeNativeV1]::BeginProcessResponding($appProcess.Id) }
                        $remainingMs = [int](1000 * ($StartupTimeoutSeconds - $clock.Elapsed.TotalSeconds))
                        if ($remainingMs -gt 0 -and $respondingTask.Wait([Math]::Min(250, $remainingMs))) {
                            $processResponding = $respondingTask.Result
                            $respondingTask = $null
                        }
                    }
                }
                $observation = [ordered]@{
                    elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
                    main_window_handle = $main
                    process_responding = $processResponding
                    wm_null_responding = $messageResponding
                    selected_window = $selected
                    visible_windows = $windows
                }
                if ([int]$clock.Elapsed.TotalSeconds -ne $lastRecorded) {
                    $report.observations += $observation
                    $lastRecorded = [int]$clock.Elapsed.TotalSeconds
                }
                $report.startup.observation = $observation
                if ($null -ne $selected -and $processResponding -and $messageResponding) {
                    if ($stableHandle -ne $selected.Handle -or $null -eq $stableSince) {
                        $stableHandle = $selected.Handle
                        $stableSince = $clock.Elapsed.TotalSeconds
                    }
                    if ($clock.Elapsed.TotalSeconds - $stableSince -ge $StableWindowSeconds) {
                        $startupObserved = $true
                        $report.startup.status = 'visible_window_responding_observed'
                        break
                    }
                } else { $stableSince = $null; $stableHandle = 0 }
                $remainingMs = [int](1000 * ($StartupTimeoutSeconds - $clock.Elapsed.TotalSeconds))
                if ($remainingMs -gt 0) { Start-Sleep -Milliseconds ([Math]::Min(200, $remainingMs)) }
            }
            $report.startup.elapsed_seconds = [Math]::Round($clock.Elapsed.TotalSeconds, 3)
            if (-not $startupObserved -and $report.startup.status -eq 'waiting_for_visible_responsive_window') {
                $report.startup.status = 'timeout_no_stable_responsive_window'
            }

            # Screenshot uses desktop pixels cropped to this process's window rectangle.
            # It does not send synchronous PrintWindow messages to a possibly hung application.
            try {
                if ($windowHandle -ne [IntPtr]::Zero -and -not $appProcess.HasExited) {
                    if (-not [CadenceGuiProbeNativeV1]::IsOwnedWindow($windowHandle, $appProcess.Id)) { throw 'Capture window no longer belongs to the launched process.' }
                    [void][CadenceGuiProbeNativeV1]::ShowWindowAsync($windowHandle, 9)
                    if (-not [CadenceGuiProbeNativeV1]::IsOwnedWindow($windowHandle, $appProcess.Id)) { throw 'Foreground window no longer belongs to the launched process.' }
                    $report.capture['foreground_requested'] = [CadenceGuiProbeNativeV1]::SetForegroundWindow($windowHandle)
                    $rect = [CadenceGuiProbeNativeV1+Rect]::new()
                    if (-not [CadenceGuiProbeNativeV1]::GetWindowRect($windowHandle, [ref]$rect)) { throw 'Window rectangle unavailable.' }
                    $left = $rect.Left; $top = $rect.Top
                    $width = $rect.Right - $rect.Left; $height = $rect.Bottom - $rect.Top
                    $report.capture.method = 'desktop_pixels_cropped_to_window_rectangle'
                } elseif ($CaptureDesktopFallback -and -not $appProcess.HasExited) {
                    $left = [CadenceGuiProbeNativeV1]::GetSystemMetrics(76); $top = [CadenceGuiProbeNativeV1]::GetSystemMetrics(77)
                    $width = [CadenceGuiProbeNativeV1]::GetSystemMetrics(78); $height = [CadenceGuiProbeNativeV1]::GetSystemMetrics(79)
                    $report.capture.method = 'entire_virtual_desktop_explicit_fallback'
                } else { throw 'No live visible window available for capture.' }
                if ($width -lt 1 -or $height -lt 1 -or [long]$width * $height -gt 40000000) { throw 'Invalid or excessive screenshot dimensions.' }
                Add-Type -AssemblyName System.Drawing
                $bitmap = [Drawing.Bitmap]::new($width, $height)
                try {
                    $graphics = [Drawing.Graphics]::FromImage($bitmap)
                    try { $graphics.CopyFromScreen($left, $top, 0, 0, $bitmap.Size) }
                    finally { $graphics.Dispose() }
                    $picture = Join-Path $artifactRoot 'gui-window.png'
                    $bitmap.Save($picture, [Drawing.Imaging.ImageFormat]::Png)
                    $report.capture.path = $picture
                    $report.capture['width'] = $width; $report.capture['height'] = $height
                    $report.capture['sha256'] = (Get-FileHash -LiteralPath $picture -Algorithm SHA256).Hash.ToLowerInvariant()
                    $report.capture.status = 'saved_requires_visual_review'
                } finally { $bitmap.Dispose() }
            } catch {
                $report.capture.status = 'unavailable'
                $report.capture.error = $_.Exception.Message
            }
            $report.status = if ($startupObserved) { 'startup_observed_shutdown_pending' } else { 'startup_failed' }
        }
    }
} catch {
    $report.status = 'probe_error'
    $report['error'] = $_.Exception.Message
    $exitStatus = 1
} finally {
    if ($null -ne $appProcess) {
        # A modal introduction can disable the main window, making CloseMainWindow
        # return false. Close only this PID's visible owned dialogs first, then its
        # main window. All requests share the same bounded graceful-close budget.
        $closeClock = [Diagnostics.Stopwatch]::StartNew()
        $postedWindows = [Collections.Generic.HashSet[long]]::new()
        try {
            $appProcess.Refresh()
            if ($appProcess.HasExited) {
                $report.shutdown.status = 'already_exited'
            } else {
                while ($closeClock.Elapsed.TotalSeconds -lt $CloseTimeoutSeconds) {
                    $appProcess.Refresh()
                    if ($appProcess.HasExited) { break }
                    $mainHandle = $appProcess.MainWindowHandle
                    $mainOwned = [CadenceGuiProbeNativeV1]::IsOwnedWindow($mainHandle, $appProcess.Id)
                    $mainEnabled = $mainOwned -and [CadenceGuiProbeNativeV1]::IsWindowEnabled($mainHandle)
                    $windows = @([CadenceGuiProbeNativeV1]::WindowsForProcess($appProcess.Id))
                    foreach ($window in $windows) {
                        if ($window.Handle -eq $mainHandle.ToInt64() -or $postedWindows.Contains($window.Handle)) { continue }
                        $ownerOwned = $window.OwnerHandle -ne 0 -and [CadenceGuiProbeNativeV1]::IsOwnedWindow([IntPtr]::new($window.OwnerHandle), $appProcess.Id)
                        # Qt can expose a modal top-level without GW_OWNER. The
                        # second case still requires the launched PID and a disabled main.
                        if (-not $ownerOwned -and -not ($mainOwned -and -not $mainEnabled -and $window.Enabled)) { continue }
                        $nativeError = 0
                        $posted = [CadenceGuiProbeNativeV1]::PostCloseOwnedWindow([IntPtr]::new($window.Handle), $appProcess.Id, [ref]$nativeError)
                        $report.shutdown.events += [ordered]@{
                            elapsed_seconds = [Math]::Round($closeClock.Elapsed.TotalSeconds, 3)
                            action = 'post_wm_close_owned_dialog'; pid = $appProcess.Id; window = $window
                            main_window_handle = $mainHandle.ToInt64(); main_enabled = $mainEnabled
                            owner_belongs_to_process = $ownerOwned; posted = $posted; native_error = $nativeError
                        }
                        if ($posted) {
                            [void]$postedWindows.Add($window.Handle)
                            $report.shutdown.owned_window_close_requested = $true
                        }
                    }
                    $appProcess.Refresh()
                    if ($appProcess.HasExited) { break }
                    $mainHandle = $appProcess.MainWindowHandle
                    # Recheck the PID immediately before asking Process to close
                    # its main window; skip a disabled main until the modal closes.
                    if (-not $report.shutdown.close_requested -and [CadenceGuiProbeNativeV1]::IsWindowEnabled($mainHandle) -and [CadenceGuiProbeNativeV1]::IsOwnedWindow($mainHandle, $appProcess.Id)) {
                        $requested = $appProcess.CloseMainWindow()
                        $report.shutdown.close_requested = $requested
                        $report.shutdown.events += [ordered]@{
                            elapsed_seconds = [Math]::Round($closeClock.Elapsed.TotalSeconds, 3)
                            action = 'close_main_window_owned_pid'; pid = $appProcess.Id
                            window_handle = $mainHandle.ToInt64(); requested = $requested
                        }
                    }
                    $remainingMs = [int](1000 * ($CloseTimeoutSeconds - $closeClock.Elapsed.TotalSeconds))
                    if ($remainingMs -gt 0 -and $appProcess.WaitForExit([Math]::Min(200, $remainingMs))) { break }
                }
                $appProcess.Refresh()
                if ($appProcess.HasExited) {
                    $report.shutdown.status = if ($report.shutdown.close_requested) { 'closed_after_close_main_window' } elseif ($report.shutdown.owned_window_close_requested) { 'closed_after_owned_window_close' } else { 'exited_without_close_request' }
                }
            }
        } catch { $report.shutdown.close_error = $_.Exception.Message }
        $report.shutdown.elapsed_seconds = [Math]::Round($closeClock.Elapsed.TotalSeconds, 3)
        try {
            $appProcess.Refresh()
            if (-not $appProcess.HasExited) {
                $report.shutdown.forced = $true
                try { $appProcess.Kill($true) }
                catch {
                    $report.shutdown['tree_kill_error'] = $_.Exception.Message
                    # Still attempt to stop the owned main process if tree cleanup failed.
                    $appProcess.Kill()
                }
                if (-not $appProcess.WaitForExit(5000)) { throw 'Owned process still alive after forced cleanup.' }
                $report.shutdown.status = if ($report.shutdown.close_error) { 'forced_cleanup_after_close_error' } else { 'forced_cleanup_after_close_timeout' }
            } elseif ($report.shutdown.status -eq 'not_started') {
                $report.shutdown.status = 'exited_after_close_error'
            }
            $report.shutdown.exit_code = $appProcess.ExitCode
            if ($startupObserved -and $report.status -ne 'probe_error') {
                if ($report.shutdown.forced) { $report.status = 'startup_observed_forced_cleanup'; $exitStatus = 3 }
                elseif (($report.shutdown.close_requested -or $report.shutdown.owned_window_close_requested) -and $report.shutdown.status -in @('closed_after_close_main_window', 'closed_after_owned_window_close') -and $report.shutdown.exit_code -eq 0) {
                    $report.status = 'startup_observed_closed_cleanly'; $exitStatus = 0
                } else { $report.status = 'startup_observed_unexpected_exit'; $exitStatus = 1 }
            } elseif ($report.shutdown.forced -and $report.status -ne 'probe_error') {
                $exitStatus = 3
            }
        } catch {
            $report.shutdown.status = 'cleanup_failed'
            $report.shutdown.error = $_.Exception.Message
            $report.status = 'cleanup_failed'
            $exitStatus = 4
        }
        $appProcess.Dispose()
    }
    $report['finished_utc'] = [DateTime]::UtcNow.ToString('o')
    $report['exit_status'] = $exitStatus
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $artifactRoot 'gui-report.json') -Encoding utf8
    Write-Host "$($report.status): $(Join-Path $artifactRoot 'gui-report.json')"
}
exit $exitStatus
