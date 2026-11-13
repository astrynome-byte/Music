// SPDX-License-Identifier: GPL-3.0-only
// Isolated native Windows qualification. All typed content is SYNTHETIC, not a credential.
#include "OwnedSecretEntry.h"
#include <sddl.h>
#include <cstdio>
#include <array>
#include <atomic>
#include <cstdlib>
using namespace cadence_owned_secret;
static HWND mainWindow=nullptr,editWindow=nullptr,labelWindow=nullptr;
static constexpr UINT Setup=WM_APP+11,Finished=WM_APP+12,CheckSynthetic=WM_APP+13;
static LRESULT CALLBACK windowProc(HWND window,UINT message,WPARAM w,LPARAM l)
{
    if(message==WM_CREATE){
        labelWindow=CreateWindowExW(0,L"STATIC",KeyLabel,WS_CHILD|WS_VISIBLE,12,12,630,25,window,nullptr,GetModuleHandleW(nullptr),nullptr);
        editWindow=CreateWindowExW(WS_EX_CLIENTEDGE,L"EDIT",L"",WS_CHILD|WS_VISIBLE|WS_TABSTOP|ES_AUTOHSCROLL|ES_PASSWORD,
                                   12,45,630,30,window,reinterpret_cast<HMENU>(101),GetModuleHandleW(nullptr),nullptr);
        return labelWindow&&editWindow?0:-1;
    }
    if(message==Setup){
        SetWindowTextW(labelWindow,w==4?L"Wrong synthetic label":KeyLabel);
        SendMessageW(editWindow,EM_SETPASSWORDCHAR,w==2?0:0x2022,0);
        SetWindowTextW(editWindow,w==3?L"Q":L"");InvalidateRect(editWindow,nullptr,TRUE);
        SetForegroundWindow(window);SetFocus(editWindow);return GetFocus()==editWindow;
    }
    if(message==CheckSynthetic){
        wchar_t synthetic[45]{};const int n=GetWindowTextW(editWindow,synthetic,45);bool equal=n==43;
        for(int i=0;i<n&&i<44;++i)if(synthetic[i]!=L'A')equal=false;SecureZeroMemory(synthetic,sizeof(synthetic));return equal;
    }
    if(message==Finished){return 0;} // The worker handle, never a message, proves completion.
    if(message==WM_CLOSE){return 0;} // Worker owns the bounded teardown; no user-close race.
    return DefWindowProcW(window,message,w,l);
}
struct Record {const char* name;bool passed;Result result;};
static std::vector<Record> records;
static std::atomic<bool> cleanup{false},completed{false};
enum class WorkerPhase : unsigned { NotStarted, ComInit, Files, Automation, Setup, Element, Entry, Check, Recorded, Cleanup, Finished };
static std::atomic<unsigned> workerPhase{0},caseIndex{0},lastResultStage{0},workerFailurePhase{0};
static std::atomic<DWORD> workerError{0};
struct Security {
    PSECURITY_DESCRIPTOR descriptor=nullptr;SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES),nullptr,FALSE};
    bool init(){Handle token;if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value))return false;DWORD size=0;GetTokenInformation(token.value,TokenUser,nullptr,0,&size);
        std::vector<BYTE> data(size);if(!size||!GetTokenInformation(token.value,TokenUser,data.data(),size,&size))return false;
        LPWSTR sid=nullptr;if(!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(data.data())->User.Sid,&sid))return false;
        const std::wstring sddl=L"O:"+std::wstring(sid)+L"D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;"+sid+L")";LocalFree(sid);
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(),SDDL_REVISION_1,&descriptor,nullptr))return false;attributes.lpSecurityDescriptor=descriptor;return true;}
    ~Security(){if(descriptor)LocalFree(descriptor);}
};
static bool writeSynthetic(const std::wstring& path,unsigned length,SECURITY_ATTRIBUTES* security,bool invalid=false,bool crlf=false)
{
    Handle file;file.value=CreateFileW(path.c_str(),GENERIC_WRITE,0,security,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);if(file.value==INVALID_HANDLE_VALUE)return false;
    std::string content(length,'A');if(invalid&&!content.empty())content.back()='!';if(crlf)content+='\r';content+='\n';DWORD written=0;return WriteFile(file.value,content.data(),static_cast<DWORD>(content.size()),&written,nullptr)&&written==content.size();
}
static DWORD WINAPI worker(void*)
{
    workerPhase.store(static_cast<unsigned>(WorkerPhase::ComInit));
    const HRESULT init=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    if(FAILED(init)){workerError.store(static_cast<DWORD>(init));workerFailurePhase.store(workerPhase.load());PostMessageW(mainWindow,Finished,0,0);return 1;}
    std::wstring folder,valid,badLength,large,link,badAlphabet,crlf;
    try{
        workerPhase.store(static_cast<unsigned>(WorkerPhase::Files));
        wchar_t env[32762]{};const DWORD length=GetEnvironmentVariableW(L"RUNNER_TEMP",env,32762);std::wstring root;
        if(!length||length>=32762||!absolute(std::wstring(env,length),root)||root.size()<=3)throw 1;
        GUID id{};wchar_t guid[40]{};if(FAILED(CoCreateGuid(&id))||!StringFromGUID2(id,guid,40))throw 1;
        folder=root+L"\\Cadence-secret-synthetic-"+guid;Security security;if(!security.init()||!CreateDirectoryW(folder.c_str(),&security.attributes))throw 1;
        valid=folder+L"\\synthetic.token";badLength=folder+L"\\short.token";large=folder+L"\\large.token";link=folder+L"\\second.token";badAlphabet=folder+L"\\alphabet.token";crlf=folder+L"\\crlf.token";
        if(!writeSynthetic(valid,43,&security.attributes)||!writeSynthetic(badLength,42,&security.attributes)||!writeSynthetic(large,100,&security.attributes)||!writeSynthetic(badAlphabet,43,&security.attributes,true)||!writeSynthetic(crlf,43,&security.attributes,false,true))throw 1;
        workerPhase.store(static_cast<unsigned>(WorkerPhase::Automation));
        ComPtr<IUIAutomation> automation;HRESULT activated=CoCreateInstance(__uuidof(CUIAutomation8),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&automation));
        if(FAILED(activated))activated=CoCreateInstance(__uuidof(CUIAutomation),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&automation));if(FAILED(activated)){workerError.store(static_cast<DWORD>(activated));throw 1;}
        Handle process;process.value=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,GetCurrentProcessId());if(!process.value||process.value==INVALID_HANDLE_VALUE)throw 1;
        auto run=[&](const char* name,WPARAM setup,const std::wstring& path,DWORD pid,bool expected,Stage rejectedAt){
            caseIndex.fetch_add(1);workerPhase.store(static_cast<unsigned>(WorkerPhase::Setup));
            if(!SendMessageW(mainWindow,Setup,setup,0))throw 1;Sleep(100);
            workerPhase.store(static_cast<unsigned>(WorkerPhase::Element));
            ComPtr<IUIAutomationElement> edit;const HRESULT elementStatus=automation->ElementFromHandle(editWindow,&edit);if(FAILED(elementStatus)||!edit){workerError.store(FAILED(elementStatus)?static_cast<DWORD>(elementStatus):ERROR_INVALID_DATA);throw 1;}
            workerPhase.store(static_cast<unsigned>(WorkerPhase::Entry));
            Result result=enter(automation.Get(),edit.Get(),pid,process.value,mainWindow,path);
            lastResultStage.store(static_cast<unsigned>(result.stage));
            workerPhase.store(static_cast<unsigned>(WorkerPhase::Check));
            const bool passed=expected?(result.passed&&result.inputCount==86&&result.maskedLength==43&&SendMessageW(mainWindow,CheckSynthetic,0,0)):
                (!result.passed&&result.inputCount==0&&result.stage==rejectedAt);
            records.push_back({name,passed,result});
            workerPhase.store(static_cast<unsigned>(WorkerPhase::Recorded));
        };
        // The valid entry happens first and is always the public, constant43'A' fixture.
        run("synthetic-43-base64url-password-entry",1,valid,GetCurrentProcessId(),true,Stage::Initial);
        run("wrong-process-id-refused",1,valid,GetCurrentProcessId()+1,false,Stage::Target);
        run("plain-text-field-refused",2,valid,GetCurrentProcessId(),false,Stage::Target);
        run("nonempty-password-field-refused",3,valid,GetCurrentProcessId(),false,Stage::Empty);
        run("wrong-accessible-label-refused",4,valid,GetCurrentProcessId(),false,Stage::Target);
        run("short-token-file-refused",1,badLength,GetCurrentProcessId(),false,Stage::File);
        run("oversized-token-file-refused",1,large,GetCurrentProcessId(),false,Stage::File);
        run("invalid-base64url-alphabet-refused",1,badAlphabet,GetCurrentProcessId(),false,Stage::File);
        run("synthetic-CRLF-token-accepted",1,crlf,GetCurrentProcessId(),true,Stage::Initial);
        run("outside-runner-temp-path-refused-before-open",1,root.substr(0,3)+L"Cadence-secret-outside-never-created.token",GetCurrentProcessId(),false,Stage::File);
        run("directory-token-refused",1,folder,GetCurrentProcessId(),false,Stage::File);
        if(!CreateHardLinkW(link.c_str(),valid.c_str(),nullptr))throw 1;
        run("multiply-linked-token-file-refused",1,valid,GetCurrentProcessId(),false,Stage::File);
        if(!DeleteFileW(link.c_str()))throw 1;link.clear();completed=true;
    }catch(...){workerFailurePhase.store(workerPhase.load());if(!workerError.load())workerError.store(GetLastError());completed=false;}
    // Only the exact fixture names beneath the freshly created owned GUID directory.
    workerPhase.store(static_cast<unsigned>(WorkerPhase::Cleanup));
    bool removed=true;
    for(const auto& path:{link,valid,badLength,large,badAlphabet,crlf})if(!path.empty()&&GetFileAttributesW(path.c_str())!=INVALID_FILE_ATTRIBUTES&&!DeleteFileW(path.c_str()))removed=false;
    if(!folder.empty()&&!RemoveDirectoryW(folder.c_str()))removed=false;cleanup=removed;
    CoUninitialize();workerPhase.store(static_cast<unsigned>(WorkerPhase::Finished));PostMessageW(mainWindow,Finished,0,0);return 0;
}
struct PumpResult {
    bool timerInjected=false,quitInjected=false,timerFixtureObserved=false,quitFixtureObserved=false;
    bool workerStarted=false,workerExited=false,timedOut=false;
    bool waitFailed=false,setupFailed=false;
    unsigned foreignTimers=0,quitMessages=0,dispatched=0;
    DWORD error=0,workerExitCode=STILL_ACTIVE;
};
static constexpr UINT_PTR OwnTimer=1;
static constexpr WPARAM FixtureQuitCode=0x434144;
static constexpr DWORD PumpMilliseconds=30000;
static int printReport(const PumpResult& pump)
{
    // The vector is touched only after the actual worker HANDLE is signaled.
    // A failed pending-worker snapshot contains atomics only, never partial records.
    bool all=pump.workerExited&&pump.workerExitCode==0&&completed.load()&&cleanup.load()
        &&!pump.timedOut&&!pump.waitFailed&&!pump.setupFailed&&records.size()==12
        &&pump.timerInjected&&pump.quitInjected&&pump.timerFixtureObserved&&pump.quitFixtureObserved&&pump.foreignTimers>=1&&pump.quitMessages>=1;
    std::printf("{\"schema_version\":1,\"scope\":\"SYNTHETIC native password Edit qualification; no Cadence app or real token\",\"observation_attempt\":2,\"worker_started\":%s,\"worker_completed\":%s,\"worker_exit_code\":%lu,\"worker_phase\":%u,\"case_index\":%u,\"last_result_stage\":%u,\"worker_error\":%lu,\"worker_failure_phase\":%u,\"process_exit_without_cpp_cleanup\":%s,\"pump\":{\"foreign_timer_injected\":%s,\"foreign_quit_injected\":%s,\"injected_timer_observed\":%s,\"injected_quit_observed\":%s,\"foreign_timer_observed\":%u,\"foreign_quit_observed\":%u,\"dispatched_messages\":%u,\"timed_out\":%s,\"wait_failed\":%s,\"setup_failed\":%s,\"error\":%lu},\"cases\":[",
        pump.workerStarted?"true":"false",pump.workerExited?"true":"false",pump.workerExitCode,workerPhase.load(),caseIndex.load(),lastResultStage.load(),workerError.load(),workerFailurePhase.load(),
        pump.workerStarted&&!pump.workerExited?"true":"false",pump.timerInjected?"true":"false",pump.quitInjected?"true":"false",pump.timerFixtureObserved?"true":"false",pump.quitFixtureObserved?"true":"false",
        pump.foreignTimers,pump.quitMessages,pump.dispatched,pump.timedOut?"true":"false",pump.waitFailed?"true":"false",pump.setupFailed?"true":"false",pump.error);
    if(pump.workerExited){
        for(std::size_t i=0;i<records.size();++i){const auto& row=records[i];all=all&&row.passed;
            std::printf("%s{\"case\":\"%s\",\"passed\":%s,\"stage\":%u,\"error\":%lu,\"input_count\":%u,\"masked_length\":%u}",
                        i?",":"",row.name,row.passed?"true":"false",static_cast<unsigned>(row.result.stage),row.result.error,row.result.inputCount,row.result.maskedLength);}
    }
    std::printf("],\"owned_temporary_files_removed\":%s,\"passed\":%s}\n",pump.workerExited&&cleanup.load()?"true":"false",all?"true":"false");
    std::fflush(stdout);return all?0:1;
}
int wmain()
{
    PumpResult pump;
    WNDCLASSW klass{};klass.lpfnWndProc=windowProc;klass.hInstance=GetModuleHandleW(nullptr);klass.lpszClassName=L"CadenceSecretSyntheticHarnessV2";
    if(!RegisterClassW(&klass)){pump.setupFailed=true;pump.error=GetLastError();printReport(pump);return 2;}
    mainWindow=CreateWindowExW(0,klass.lpszClassName,L"Cadence secret entry — synthetic native harness",WS_OVERLAPPEDWINDOW,
                              CW_USEDEFAULT,CW_USEDEFAULT,700,170,nullptr,nullptr,klass.hInstance,nullptr);
    if(!mainWindow){pump.setupFailed=true;pump.error=GetLastError();printReport(pump);return 2;}
    ShowWindow(mainWindow,SW_SHOW);UpdateWindow(mainWindow);
    if(!SetTimer(mainWindow,OwnTimer,PumpMilliseconds,nullptr)){
        pump.setupFailed=true;pump.error=GetLastError();DestroyWindow(mainWindow);printReport(pump);return 2;
    }
    // Deterministic regression: these are this test's own queued thread messages.
    // V1 stopped on either of them, independently of worker/UIA completion.
    pump.timerInjected=PostThreadMessageW(GetCurrentThreadId(),WM_TIMER,OwnTimer,0)!=FALSE;
    pump.quitInjected=PostThreadMessageW(GetCurrentThreadId(),WM_QUIT,FixtureQuitCode,0)!=FALSE;
    if(!pump.timerInjected||!pump.quitInjected){
        pump.setupFailed=true;pump.error=GetLastError();KillTimer(mainWindow,OwnTimer);DestroyWindow(mainWindow);printReport(pump);return 2;
    }
    const ULONGLONG deadline=GetTickCount64()+PumpMilliseconds;
    Handle thread;thread.value=CreateThread(nullptr,0,worker,nullptr,0,nullptr);
    if(!thread.value){pump.setupFailed=true;pump.error=GetLastError();KillTimer(mainWindow,OwnTimer);DestroyWindow(mainWindow);printReport(pump);return 2;}
    pump.workerStarted=true;
    for(;;){
        const ULONGLONG now=GetTickCount64();
        if(now>=deadline){pump.timedOut=true;break;}
        const DWORD wait=MsgWaitForMultipleObjectsEx(1,&thread.value,static_cast<DWORD>(deadline-now),QS_ALLINPUT,MWMO_INPUTAVAILABLE);
        if(wait==WAIT_OBJECT_0){pump.workerExited=true;break;}
        if(wait==WAIT_TIMEOUT){pump.timedOut=true;break;}
        if(wait==WAIT_FAILED){pump.waitFailed=true;pump.error=GetLastError();break;}
        if(wait!=WAIT_OBJECT_0+1){pump.waitFailed=true;pump.error=ERROR_INVALID_DATA;break;}
        MSG message{};
        // Sent messages (including the worker's synchronous Setup) are serviced
        // by PeekMessage. Limit each queue batch so the worker handle/deadline
        // cannot be starved by unrelated providers or an endlessly busy queue.
        for(unsigned batch=0;batch<256&&PeekMessageW(&message,nullptr,0,0,PM_REMOVE);++batch){
            if(GetTickCount64()>=deadline){pump.timedOut=true;break;}
            if(message.message==WM_QUIT){++pump.quitMessages;if(message.hwnd==nullptr&&message.wParam==FixtureQuitCode&&message.lParam==0)pump.quitFixtureObserved=true;continue;}
            if(message.message==WM_TIMER){
                if(message.hwnd==mainWindow&&message.wParam==OwnTimer){pump.timedOut=true;break;}
                ++pump.foreignTimers; // Still dispatch genuine provider timers.
                if(message.hwnd==nullptr&&message.wParam==OwnTimer&&message.lParam==0)pump.timerFixtureObserved=true;
            }
            TranslateMessage(&message);DispatchMessageW(&message);++pump.dispatched;
        }
        if(pump.timedOut)break;
    }
    // A last nonblocking HANDLE check is legitimate even on a pump failure;
    // no second wait is allowed to starve a still-running provider of messages.
    if(!pump.workerExited)pump.workerExited=WaitForSingleObject(thread.value,0)==WAIT_OBJECT_0;
    if(pump.workerExited){
        if(!GetExitCodeThread(thread.value,&pump.workerExitCode)){pump.waitFailed=true;pump.error=GetLastError();}
        KillTimer(mainWindow,OwnTimer);DestroyWindow(mainWindow);
        return printReport(pump);
    }
    printReport(pump);
    // No global C++ destructors may race the active worker's vector or strings.
    // This is an explicitly FAILED bounded synthetic child, not clean teardown.
    // The wrapper retains its false cleanup/worker flags and nonzero exit.
    std::_Exit(3);
}
