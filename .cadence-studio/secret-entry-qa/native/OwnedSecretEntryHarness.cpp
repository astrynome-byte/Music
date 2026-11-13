// SPDX-License-Identifier: GPL-3.0-only
// Isolated native Windows qualification. All typed content is SYNTHETIC, not a credential.
#include "OwnedSecretEntry.h"
#include <sddl.h>
#include <cstdio>
#include <array>
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
    if(message==Finished){PostQuitMessage(0);return 0;}
    if(message==WM_CLOSE){return 0;} // Worker owns the bounded teardown; no user-close race.
    return DefWindowProcW(window,message,w,l);
}
struct Record {const char* name;bool passed;Result result;};
static std::vector<Record> records;static bool cleanup=false,completed=false;
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
    const HRESULT init=CoInitializeEx(nullptr,COINIT_MULTITHREADED);if(FAILED(init)){PostMessageW(mainWindow,Finished,0,0);return 1;}
    std::wstring folder,valid,badLength,large,link,badAlphabet,crlf;
    try{
        wchar_t env[32762]{};const DWORD length=GetEnvironmentVariableW(L"RUNNER_TEMP",env,32762);std::wstring root;
        if(!length||length>=32762||!absolute(std::wstring(env,length),root)||root.size()<=3)throw 1;
        GUID id{};wchar_t guid[40]{};if(FAILED(CoCreateGuid(&id))||!StringFromGUID2(id,guid,40))throw 1;
        folder=root+L"\\Cadence-secret-synthetic-"+guid;Security security;if(!security.init()||!CreateDirectoryW(folder.c_str(),&security.attributes))throw 1;
        valid=folder+L"\\synthetic.token";badLength=folder+L"\\short.token";large=folder+L"\\large.token";link=folder+L"\\second.token";badAlphabet=folder+L"\\alphabet.token";crlf=folder+L"\\crlf.token";
        if(!writeSynthetic(valid,43,&security.attributes)||!writeSynthetic(badLength,42,&security.attributes)||!writeSynthetic(large,100,&security.attributes)||!writeSynthetic(badAlphabet,43,&security.attributes,true)||!writeSynthetic(crlf,43,&security.attributes,false,true))throw 1;
        ComPtr<IUIAutomation> automation;HRESULT activated=CoCreateInstance(__uuidof(CUIAutomation8),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&automation));
        if(FAILED(activated))activated=CoCreateInstance(__uuidof(CUIAutomation),nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&automation));if(FAILED(activated))throw 1;
        Handle process;process.value=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,GetCurrentProcessId());if(!process.value||process.value==INVALID_HANDLE_VALUE)throw 1;
        auto run=[&](const char* name,WPARAM setup,const std::wstring& path,DWORD pid,bool expected,Stage rejectedAt){
            if(!SendMessageW(mainWindow,Setup,setup,0))throw 1;Sleep(100);
            ComPtr<IUIAutomationElement> edit;if(FAILED(automation->ElementFromHandle(editWindow,&edit))||!edit)throw 1;
            Result result=enter(automation.Get(),edit.Get(),pid,process.value,mainWindow,path);
            const bool passed=expected?(result.passed&&result.inputCount==86&&result.maskedLength==43&&SendMessageW(mainWindow,CheckSynthetic,0,0)):
                (!result.passed&&result.inputCount==0&&result.stage==rejectedAt);
            records.push_back({name,passed,result});
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
    }catch(...){completed=false;}
    // Only the four exact names beneath the freshly created owned GUID directory.
    bool removed=true;
    for(const auto& path:{link,valid,badLength,large,badAlphabet,crlf})if(!path.empty()&&GetFileAttributesW(path.c_str())!=INVALID_FILE_ATTRIBUTES&&!DeleteFileW(path.c_str()))removed=false;
    if(!folder.empty()&&!RemoveDirectoryW(folder.c_str()))removed=false;cleanup=removed;
    CoUninitialize();PostMessageW(mainWindow,Finished,0,0);return 0;
}
int wmain()
{
    WNDCLASSW klass{};klass.lpfnWndProc=windowProc;klass.hInstance=GetModuleHandleW(nullptr);klass.lpszClassName=L"CadenceSecretSyntheticHarness";
    if(!RegisterClassW(&klass))return 2;
    mainWindow=CreateWindowExW(0,klass.lpszClassName,L"Cadence secret entry — synthetic native harness",WS_OVERLAPPEDWINDOW,
                              CW_USEDEFAULT,CW_USEDEFAULT,700,170,nullptr,nullptr,klass.hInstance,nullptr);
    if(!mainWindow)return 2;ShowWindow(mainWindow,SW_SHOW);UpdateWindow(mainWindow);
    // A finite checked timer exists before the worker can call a provider.
    if(!SetTimer(mainWindow,1,30000,nullptr)){DestroyWindow(mainWindow);return 2;}
    Handle thread;thread.value=CreateThread(nullptr,0,worker,nullptr,0,nullptr);if(!thread.value){KillTimer(mainWindow,1);DestroyWindow(mainWindow);return 2;}
    MSG message{};bool timedOut=false;
    while(GetMessageW(&message,nullptr,0,0)>0){if(message.message==WM_TIMER&&message.wParam==1){timedOut=true;break;}TranslateMessage(&message);DispatchMessageW(&message);}
    const bool exited=WaitForSingleObject(thread.value,5000)==WAIT_OBJECT_0;
    if(!exited)return 3;KillTimer(mainWindow,1);DestroyWindow(mainWindow);
    bool all=completed&&cleanup&&!timedOut&&records.size()==12;
    std::printf("{\"schema_version\":1,\"scope\":\"SYNTHETIC native password Edit qualification; no Cadence app or real token\",\"cases\":[");
    for(std::size_t i=0;i<records.size();++i){const auto& row=records[i];all=all&&row.passed;
        std::printf("%s{\"case\":\"%s\",\"passed\":%s,\"stage\":%u,\"error\":%lu,\"input_count\":%u,\"masked_length\":%u}",
                    i?",":"",row.name,row.passed?"true":"false",static_cast<unsigned>(row.result.stage),row.result.error,row.result.inputCount,row.result.maskedLength);}
    std::printf("],\"owned_temporary_files_removed\":%s,\"passed\":%s}\n",cleanup?"true":"false",all?"true":"false");return all?0:1;
}
