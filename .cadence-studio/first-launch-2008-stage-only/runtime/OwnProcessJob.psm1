# SPDX-License-Identifier: GPL-3.0-only
# Source preparation only: importing defines functions and makes no native call.
# Create this anonymous nested Job for the current CI pwsh BEFORE spawning QA
# children. Descendants inherit membership; no breakaway permission is granted.
# Failed Stop/Close retains a strong Job-handle reference until pwsh exits.
# KILL remains armed on ordinary failures. A native close plus rearm failure is
# reported explicitly as unconfirmed; Close must be the final operation that
# could affect processes. Afterwards only write diagnostics and exit pwsh.
#Requires -Version 7.2
Set-StrictMode -Version Latest

function Assert-OwnedJobHost {
    if(-not [OperatingSystem]::IsWindows() -or -not [Environment]::Is64BitProcess -or
       [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
       [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne 'X64' -or
       $env:CI -ne 'true' -or $env:GITHUB_ACTIONS -ne 'true' -or
       $env:RUNNER_ENVIRONMENT -ne 'github-hosted'){
        throw 'Owned Job requires disposable native Windows x64 GitHub-hosted CI; no native call made.'
    }
}

function Initialize-OwnedJobTypes {
    if('Cadence.Qa.OwnedProcessJobV1' -as [type]){return}
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

namespace Cadence.Qa {
    [StructLayout(LayoutKind.Sequential)]
    internal struct JobAccountingV1 {
        internal long TotalUserTime, TotalKernelTime, ThisPeriodTotalUserTime, ThisPeriodTotalKernelTime;
        internal uint TotalPageFaultCount, TotalProcesses, ActiveProcesses, TotalTerminatedProcesses;
    }
    [StructLayout(LayoutKind.Sequential)]
    internal struct JobBasicLimitsV1 {
        internal long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        internal uint LimitFlags;
        internal UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        internal uint ActiveProcessLimit;
        internal UIntPtr Affinity;
        internal uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    internal struct JobIoCountersV1 {
        internal ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        internal ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }
    [StructLayout(LayoutKind.Sequential)]
    internal struct JobExtendedLimitsV1 {
        internal JobBasicLimitsV1 Basic;
        internal JobIoCountersV1 Io;
        internal UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    internal static class OwnedJobNativeV1 {
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        internal static extern IntPtr CreateJobObjectW(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", SetLastError=true)]
        internal static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll", SetLastError=true)]
        internal static extern uint GetCurrentProcessId();
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool SetInformationJobObject(IntPtr job, int kind, ref JobExtendedLimitsV1 data, uint size);
        [DllImport("kernel32.dll", EntryPoint="QueryInformationJobObject", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool QueryLimits(IntPtr job, int kind, out JobExtendedLimitsV1 data, uint size, out uint returned);
        [DllImport("kernel32.dll", EntryPoint="QueryInformationJobObject", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool QueryAccounting(IntPtr job, int kind, out JobAccountingV1 data, uint size, out uint returned);
        [DllImport("kernel32.dll", EntryPoint="QueryInformationJobObject", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool QueryProcessIds(IntPtr job, int kind, IntPtr data, uint size, out uint returned);
        [DllImport("kernel32.dll", SetLastError=true)]
        internal static extern IntPtr OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, uint pid);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool IsProcessInJob(IntPtr process, IntPtr job, [MarshalAs(UnmanagedType.Bool)] out bool inside);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool TerminateProcess(IntPtr process, uint exitCode);
        [DllImport("kernel32.dll", SetLastError=true)]
        internal static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CloseHandle(IntPtr handle);
    }
    public sealed class OwnedJobDrainProofV1 {
        public uint ControllerPid { get; internal set; }
        public uint ActiveProcesses { get; internal set; }
        public uint[] ProcessIds { get; internal set; }
        public uint[] TerminatedPids { get; internal set; }
        public uint[] AlreadyExitedPids { get; internal set; }
        public bool ChildrenDrained { get; internal set; }
        public int MaximumProcessIds { get; internal set; }
        public long ElapsedMilliseconds { get; internal set; }
        public bool KillOnJobCloseArmed { get; internal set; }
    }
    public sealed class OwnedProcessJobV1 : IDisposable {
        public const int MaximumProcessIds = 128;
        public const uint KillOnJobClose = 0x00002000;
        // IsProcessInJob requires QUERY_LIMITED_INFORMATION in addition to the
        // TERMINATE and SYNCHRONIZE rights needed for termination and waiting.
        public const uint PinnedProcessAccess = 0x00101001;
        private const uint WaitObject = 0, WaitTimeout = 258, WaitFailed = 0xffffffff;
        private static readonly HashSet<OwnedProcessJobV1> LiveScopes = new HashSet<OwnedProcessJobV1>();
        private readonly object gate = new object();
        private readonly uint controller;
        private IntPtr handle;
        private bool closed;
        public string KillArmState {get; private set;}

        private OwnedProcessJobV1(IntPtr job, uint pid) { handle=job; controller=pid;KillArmState="not-yet-armed"; }
        private static void RequireHost() {
            if(!RuntimeInformation.IsOSPlatform(OSPlatform.Windows) || IntPtr.Size!=8 ||
               RuntimeInformation.OSArchitecture!=Architecture.X64 || RuntimeInformation.ProcessArchitecture!=Architecture.X64 ||
               Environment.GetEnvironmentVariable("CI")!="true" ||
               Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true" ||
               Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")!="github-hosted")
                throw new InvalidOperationException("Only disposable native Windows x64 GitHub-hosted CI may invoke native Job APIs.");
        }
        private static Exception NativeError(string operation) {
            return new Win32Exception(Marshal.GetLastWin32Error(),operation);
        }
        private static void AssertLayouts() {
            if(Marshal.SizeOf<JobAccountingV1>()!=48 || Marshal.SizeOf<JobBasicLimitsV1>()!=64 ||
               Marshal.SizeOf<JobIoCountersV1>()!=48 || Marshal.SizeOf<JobExtendedLimitsV1>()!=144)
                throw new InvalidOperationException("Unexpected native x64 Job structure layout.");
        }
        private void RequireOpenController() {
            RequireHost();
            if(closed || handle==IntPtr.Zero) throw new ObjectDisposedException("OwnedProcessJobV1");
            if(OwnedJobNativeV1.GetCurrentProcessId()!=controller)
                throw new InvalidOperationException("Only the original pwsh controller may use this Job.");
            bool inside;
            if(!OwnedJobNativeV1.IsProcessInJob(OwnedJobNativeV1.GetCurrentProcess(),handle,out inside))
                throw NativeError("Cannot check controller Job membership");
            if(!inside) throw new InvalidOperationException("Controller is no longer in its exact owned Job.");
        }
        private void SetLimits(ref JobExtendedLimitsV1 limits) {
            if(!OwnedJobNativeV1.SetInformationJobObject(handle,9,ref limits,(uint)Marshal.SizeOf<JobExtendedLimitsV1>()))
                throw NativeError("Cannot set owned Job extended limits");
        }
        private JobExtendedLimitsV1 ReadLimits() {
            JobExtendedLimitsV1 limits; uint returned;
            if(!OwnedJobNativeV1.QueryLimits(handle,9,out limits,(uint)Marshal.SizeOf<JobExtendedLimitsV1>(),out returned))
                throw NativeError("Cannot query owned Job extended limits");
            if(returned!=144) throw new InvalidOperationException("Unexpected Job limit query size.");
            return limits;
        }
        private JobAccountingV1 ReadAccounting() {
            JobAccountingV1 accounting; uint returned;
            if(!OwnedJobNativeV1.QueryAccounting(handle,1,out accounting,(uint)Marshal.SizeOf<JobAccountingV1>(),out returned))
                throw NativeError("Cannot query owned Job accounting");
            if(returned!=48 || accounting.ActiveProcesses<1 || accounting.ActiveProcesses>MaximumProcessIds)
                throw new InvalidOperationException("Owned Job active process count/structure exceeds its contract.");
            return accounting;
        }
        private uint[] ReadProcessIds() {
            // JOBOBJECT_BASIC_PROCESS_ID_LIST: two DWORDs, then ULONG_PTR[].
            int capacity=8+MaximumProcessIds*IntPtr.Size;
            IntPtr buffer=Marshal.AllocHGlobal(capacity);
            try {
                uint returned;
                if(!OwnedJobNativeV1.QueryProcessIds(handle,3,buffer,(uint)capacity,out returned))
                    throw NativeError("Bounded Job PID query failed (including ERROR_MORE_DATA); no truncated list accepted");
                uint assigned=unchecked((uint)Marshal.ReadInt32(buffer,0));
                uint listed=unchecked((uint)Marshal.ReadInt32(buffer,4));
                if(assigned<1 || assigned>MaximumProcessIds || listed!=assigned ||
                   returned<8+listed*8 || returned>(uint)capacity)
                    throw new InvalidOperationException("Incomplete or oversized owned Job PID list.");
                var result=new uint[listed];var unique=new HashSet<uint>();
                for(int index=0;index<result.Length;index++) {
                    ulong raw=unchecked((ulong)Marshal.ReadInt64(buffer,8+index*8));
                    if(raw==0 || raw>uint.MaxValue || !unique.Add((uint)raw))
                        throw new InvalidOperationException("Invalid, truncated or duplicate native process identifier.");
                    result[index]=(uint)raw;
                }
                if(!unique.Contains(controller)) throw new InvalidOperationException("Owned Job PID list lost its controller.");
                return result;
            } finally { Marshal.FreeHGlobal(buffer); }
        }
        private bool AnchorOnly(out uint[] ids, out JobAccountingV1 accounting) {
            ids=ReadProcessIds();accounting=ReadAccounting();
            return ids.Length==1 && ids[0]==controller && accounting.ActiveProcesses==1;
        }
        private OwnedJobDrainProofV1 FreshAnchorProof() {
            uint[] first,second;JobAccountingV1 firstAccounting,secondAccounting;
            if(!AnchorOnly(out first,out firstAccounting) || !AnchorOnly(out second,out secondAccounting))
                throw new InvalidOperationException("Owned children remain; the Job cannot be disarmed or treated as drained.");
            return new OwnedJobDrainProofV1 {ControllerPid=controller,ActiveProcesses=secondAccounting.ActiveProcesses,
                ProcessIds=second,TerminatedPids=new uint[0],AlreadyExitedPids=new uint[0],ChildrenDrained=true,
                MaximumProcessIds=MaximumProcessIds,ElapsedMilliseconds=0,KillOnJobCloseArmed=true};
        }
        public static OwnedProcessJobV1 Create() {
            RequireHost();AssertLayouts();
            // Null security attributes => the anonymous Job handle is not inheritable.
            IntPtr native=OwnedJobNativeV1.CreateJobObjectW(IntPtr.Zero,null);
            if(native==IntPtr.Zero || native==new IntPtr(-1)) throw NativeError("Cannot create anonymous owned Job");
            var scope=new OwnedProcessJobV1(native,OwnedJobNativeV1.GetCurrentProcessId());
            bool assigned=false;
            try {
                var limits=new JobExtendedLimitsV1();limits.Basic.LimitFlags=KillOnJobClose;
                scope.SetLimits(ref limits);
                if(scope.ReadLimits().Basic.LimitFlags!=KillOnJobClose)
                    throw new InvalidOperationException("New Job must arm KILL_ON_JOB_CLOSE and grant no breakaway flags.");
                scope.KillArmState="armed-confirmed";
                if(!OwnedJobNativeV1.AssignProcessToJobObject(native,OwnedJobNativeV1.GetCurrentProcess()))
                    throw NativeError("Cannot assign current pwsh to the nested Job before spawning");
                assigned=true;
                lock(LiveScopes) { LiveScopes.Add(scope); }
                scope.RequireOpenController();scope.FreshAnchorProof();
                return scope;
            } catch {
                // Once assigned, never release an armed handle during exception
                // unwinding: keep it rooted until pwsh exits after diagnostics.
                if(assigned) { lock(LiveScopes) { LiveScopes.Add(scope); } }
                else { OwnedJobNativeV1.CloseHandle(native);scope.handle=IntPtr.Zero;scope.closed=true; }
                throw;
            }
        }
        public OwnedJobDrainProofV1 StopChildren(int timeoutMilliseconds) {
            lock(gate) {
                RequireOpenController();
                if(timeoutMilliseconds<100 || timeoutMilliseconds>30000)
                    throw new ArgumentOutOfRangeException("timeoutMilliseconds");
                if(ReadLimits().Basic.LimitFlags!=KillOnJobClose)
                    throw new InvalidOperationException("Owned Job lost its armed, no-breakaway limit contract.");
                var timer=Stopwatch.StartNew();var terminated=new HashSet<uint>();var exited=new HashSet<uint>();
                while(timer.ElapsedMilliseconds<timeoutMilliseconds) {
                    uint[] ids;JobAccountingV1 accounting;
                    if(AnchorOnly(out ids,out accounting)) {
                        var proof=FreshAnchorProof();
                        proof.TerminatedPids=new List<uint>(terminated).ToArray();
                        proof.AlreadyExitedPids=new List<uint>(exited).ToArray();
                        proof.ElapsedMilliseconds=timer.ElapsedMilliseconds;
                        return proof;
                    }
                    foreach(uint pid in ids) {
                        if(pid==controller) continue;
                        IntPtr process=OwnedJobNativeV1.OpenProcess(PinnedProcessAccess,false,pid);
                        if(process==IntPtr.Zero) {
                            int error=Marshal.GetLastWin32Error();
                            if(error==87) {exited.Add(pid);continue;} // Vanished PID; only a fresh Job query can prove drainage.
                            throw new Win32Exception(error,"Cannot pin an owned Job child for termination/wait");
                        }
                        try {
                            uint state=OwnedJobNativeV1.WaitForSingleObject(process,0);
                            if(state==WaitObject) {exited.Add(pid);continue;}
                            if(state==WaitFailed) throw NativeError("Cannot query pinned child exit state");
                            if(state!=WaitTimeout) throw new InvalidOperationException("Unexpected child wait result.");
                            bool inside;
                            if(!OwnedJobNativeV1.IsProcessInJob(process,handle,out inside))
                                throw NativeError("Cannot confirm pinned child membership");
                            if(!inside) throw new InvalidOperationException("PID reuse or foreign process detected; termination refused.");
                            // This exact process handle remains open from the
                            // membership check through termination and waiting.
                            if(!OwnedJobNativeV1.TerminateProcess(process,0xcace0002)) {
                                int error=Marshal.GetLastWin32Error();
                                if(OwnedJobNativeV1.WaitForSingleObject(process,0)!=WaitObject)
                                    throw new Win32Exception(error,"Cannot terminate an exact owned Job child");
                                exited.Add(pid);
                            } else {terminated.Add(pid);}
                            long remaining=timeoutMilliseconds-timer.ElapsedMilliseconds;
                            if(remaining<=0) throw new TimeoutException("Owned Job drain deadline exceeded.");
                            state=OwnedJobNativeV1.WaitForSingleObject(process,(uint)remaining);
                            if(state==WaitFailed) throw NativeError("Cannot wait for pinned owned child");
                            if(state!=WaitObject) throw new TimeoutException("Owned Job child did not drain before the deadline.");
                        } finally {
                            if(!OwnedJobNativeV1.CloseHandle(process)) throw NativeError("Cannot close pinned process handle");
                        }
                    }
                    Thread.Sleep(10);
                }
                throw new TimeoutException("Fresh Job queries did not prove pwsh is the sole active process.");
            }
        }
        public OwnedJobDrainProofV1 CloseNormally() {
            lock(gate) {
                RequireOpenController();
                var proof=FreshAnchorProof();
                var limits=ReadLimits();
                if(limits.Basic.LimitFlags!=KillOnJobClose)
                    throw new InvalidOperationException("Unexpected Job flags; retain handle and fail closed.");
                limits.Basic.LimitFlags &= ~KillOnJobClose;
                SetLimits(ref limits);
                KillArmState="disarmed-after-anchor-only-proof";
                if(!OwnedJobNativeV1.CloseHandle(handle)) {
                    int error=Marshal.GetLastWin32Error();
                    // Do not let a rare close failure leave a live scope disarmed.
                    limits.Basic.LimitFlags=KillOnJobClose;
                    try {
                        SetLimits(ref limits);
                        if(ReadLimits().Basic.LimitFlags!=KillOnJobClose)
                            throw new InvalidOperationException("KILL_ON_JOB_CLOSE rearm did not verify.");
                        KillArmState="armed-confirmed";
                    } catch(Exception rearmError) {
                        KillArmState="KillOnJobClose-unconfirmed-after-native-close-and-rearm-failure";
                        throw new AggregateException("Close failed and KillOnJobClose is unconfirmed. The Job handle remains retained; do not spawn or resume work. Record failure and exit pwsh.",
                            new Win32Exception(error,"Cannot close owned Job normally"),rearmError);
                    }
                    throw new Win32Exception(error,"Cannot close owned Job normally");
                }
                handle=IntPtr.Zero;closed=true;
                KillArmState="closed-after-anchor-only-proof";
                lock(LiveScopes) { LiveScopes.Remove(this); }
                proof.KillOnJobCloseArmed=false;
                return proof;
            }
        }
        public void Dispose() { lock(gate) {if(!closed) CloseNormally();} }
    }
}
'@
}

function New-OwnedProcessJob {
    [CmdletBinding()]
    param()
    Assert-OwnedJobHost
    Initialize-OwnedJobTypes
    [Cadence.Qa.OwnedProcessJobV1]::Create()
}
function Stop-OwnedJobChildren {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Job,
          [ValidateRange(100,30000)][int]$TimeoutMilliseconds=20000)
    Assert-OwnedJobHost
    if($Job.GetType().FullName -cne 'Cadence.Qa.OwnedProcessJobV1'){throw 'An exact owned Job object is required.'}
    $Job.StopChildren($TimeoutMilliseconds)
}
function Close-OwnedProcessJob {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Job)
    Assert-OwnedJobHost
    if($Job.GetType().FullName -cne 'Cadence.Qa.OwnedProcessJobV1'){throw 'An exact owned Job object is required.'}
    $Job.CloseNormally()
}
Export-ModuleMember -Function New-OwnedProcessJob,Stop-OwnedJobChildren,Close-OwnedProcessJob
