// SPDX-License-Identifier: GPL-3.0-only
// Private QA only. No credential, path, text, token hash, clipboard or log output.
#pragma once
#include <windows.h>
#include <UIAutomation.h>
#include <aclapi.h>
#include <wrl/client.h>
#include <algorithm>
#include <cstdint>
#include <cwchar>
#include <string>
#include <vector>
#include "OwnedKeyboard.h"

namespace cadence_owned_secret {
using Microsoft::WRL::ComPtr;
constexpr wchar_t KeyLabel[] = L"Clé privée d’appareil, utilisée seulement dans cette fenêtre";
enum class Stage : unsigned { Initial, File, Target, Empty, Input, Mask, Complete };
struct Result { bool passed=false; DWORD error=ERROR_SUCCESS; Stage stage=Stage::Initial; UINT inputCount=0; unsigned maskedLength=0; };
struct Handle { HANDLE value=INVALID_HANDLE_VALUE; ~Handle(){if(value!=INVALID_HANDLE_VALUE&&value)CloseHandle(value);} };
struct Secret { char bytes[45]{}; ~Secret(){SecureZeroMemory(bytes,sizeof(bytes));} };
struct InputBuffer { std::vector<INPUT> data; ~InputBuffer(){if(!data.empty())SecureZeroMemory(data.data(),data.size()*sizeof(INPUT));} };
struct Text { BSTR value=nullptr; ~Text(){if(value){SecureZeroMemory(value,SysStringLen(value)*sizeof(wchar_t));SysFreeString(value);}} };
inline Result failed(Stage stage,DWORD error){Result r;r.stage=stage;r.error=error?error:ERROR_ACCESS_DENIED;return r;}
inline bool same(const std::wstring& a,const std::wstring& b){return CompareStringOrdinal(a.c_str(),-1,b.c_str(),-1,TRUE)==CSTR_EQUAL;}
inline bool absolute(const std::wstring& path,std::wstring& full)
{
    if(path.size()<3||path.size()>32760||!((path[0]>=L'A'&&path[0]<=L'Z')||(path[0]>=L'a'&&path[0]<=L'z'))||path[1]!=L':'||path[2]!=L'\\'
       ||path.find(L'\0')!=std::wstring::npos||path.find(L':',2)!=std::wstring::npos||path.find(L'/')!=std::wstring::npos)return false;
    const DWORD size=GetFullPathNameW(path.c_str(),0,nullptr,nullptr);if(!size||size>32761)return false;
    std::vector<wchar_t> buf(size);const DWORD got=GetFullPathNameW(path.c_str(),size,buf.data(),nullptr);if(!got||got>=size)return false;
    full.assign(buf.data(),got);while(full.size()>3&&full.back()==L'\\')full.pop_back();return true;
}
inline bool ownedByCurrentUser(HANDLE object)
{
    Handle token;if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token.value))return false;
    DWORD needed=0;GetTokenInformation(token.value,TokenUser,nullptr,0,&needed);if(!needed||needed>65536)return false;
    std::vector<BYTE> user(needed);if(!GetTokenInformation(token.value,TokenUser,user.data(),needed,&needed))return false;
    PSID owner=nullptr;PSECURITY_DESCRIPTOR security=nullptr;
    const DWORD code=GetSecurityInfo(object,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION,&owner,nullptr,nullptr,nullptr,&security);
    const bool valid=code==ERROR_SUCCESS&&owner&&IsValidSid(owner)&&EqualSid(owner,reinterpret_cast<TOKEN_USER*>(user.data())->User.Sid);
    if(security)LocalFree(security);return valid;
}
inline bool normalObject(HANDLE file,bool directory)
{
    FILE_ATTRIBUTE_TAG_INFO attrs{};BY_HANDLE_FILE_INFORMATION info{};
    return GetFileType(file)==FILE_TYPE_DISK&&GetFileInformationByHandleEx(file,FileAttributeTagInfo,&attrs,sizeof(attrs))
        &&!(attrs.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)&&bool(attrs.FileAttributes&FILE_ATTRIBUTE_DIRECTORY)==directory
        &&GetFileInformationByHandle(file,&info)&&(directory||(info.nNumberOfLinks==1&&ownedByCurrentUser(file)));
}
inline bool readSecret(const std::wstring& supplied,Secret& secret)
{
    const DWORD envSize=GetEnvironmentVariableW(L"RUNNER_TEMP",nullptr,0);if(!envSize||envSize>32761)return false;
    std::vector<wchar_t> env(envSize);if(GetEnvironmentVariableW(L"RUNNER_TEMP",env.data(),envSize)>=envSize)return false;
    std::wstring root,path;if(!absolute(env.data(),root)||!absolute(supplied,path))return false;
    if(path.size()<=root.size()+1||!same(path.substr(0,root.size()),root)||path[root.size()]!=L'\\')return false;
    // Open every directory at and below RUNNER_TEMP without following reparse points.
    for(std::size_t end=root.size();;){
        const std::wstring folder=path.substr(0,end);Handle dir;
        dir.value=CreateFileW(folder.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,
                             FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
        if(dir.value==INVALID_HANDLE_VALUE||!normalObject(dir.value,true))return false;
        const auto next=path.find(L'\\',end+1);if(next==std::wstring::npos)break;end=next;
    }
    Handle file;file.value=CreateFileW(path.c_str(),GENERIC_READ|READ_CONTROL,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_SEQUENTIAL_SCAN,nullptr);
    if(file.value==INVALID_HANDLE_VALUE||!normalObject(file.value,false))return false;
    const DWORD finalSize=GetFinalPathNameByHandleW(file.value,nullptr,0,FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
    if(!finalSize||finalSize>32761)return false;
    std::vector<wchar_t> finalPath(finalSize+1);const DWORD got=GetFinalPathNameByHandleW(file.value,finalPath.data(),static_cast<DWORD>(finalPath.size()),FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
    if(!got||got>=finalPath.size())return false;
    std::wstring final(finalPath.data(),got);if(final.rfind(L"\\\\?\\",0)==0)final.erase(0,4);
    if(!same(final,path))return false;
    LARGE_INTEGER length{};if(!GetFileSizeEx(file.value,&length)||(length.QuadPart!=44&&length.QuadPart!=45))return false;
    DWORD read=0;if(!ReadFile(file.value,secret.bytes,static_cast<DWORD>(length.QuadPart),&read,nullptr)||read!=length.QuadPart)return false;
    if((read==44&&secret.bytes[43]!='\n')||(read==45&&(secret.bytes[43]!='\r'||secret.bytes[44]!='\n')))return false;
    for(unsigned i=0;i<43;++i){const char c=secret.bytes[i];if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='-'))return false;}
    return true;
}
inline bool target(IUIAutomation* automation,IUIAutomationElement* edit,DWORD pid,HANDLE process,HWND window)
{
    if(!automation||!edit)return false;
    DWORD error=0;OwnedKeyResult focus;
    if(!cadence_owned_keyboard_detail::processAlive(pid,process,error)||!cadence_owned_keyboard_detail::windowOwned(window,pid)
       ||!IsWindowVisible(window)||!IsWindowEnabled(window)||cadence_owned_keyboard_detail::modifiersDown()
       ||!cadence_owned_keyboard_detail::sampleOwnedFocus(pid,focus)||focus.foreground!=window)return false;
    int actualPid=0,type=0;BOOL enabled=FALSE,offscreen=TRUE,password=FALSE;Text name;
    if(FAILED(edit->get_CurrentProcessId(&actualPid))||actualPid!=static_cast<int>(pid)||FAILED(edit->get_CurrentControlType(&type))||type!=UIA_EditControlTypeId
       ||FAILED(edit->get_CurrentIsEnabled(&enabled))||!enabled||FAILED(edit->get_CurrentIsOffscreen(&offscreen))||offscreen
       ||FAILED(edit->get_CurrentIsPassword(&password))||!password||FAILED(edit->get_CurrentName(&name.value))||!name.value
       ||std::wstring(name.value,SysStringLen(name.value))!=KeyLabel)return false;
    ComPtr<IUIAutomationElement> active;BOOL equal=FALSE;
    return SUCCEEDED(automation->GetFocusedElement(&active))&&active&&SUCCEEDED(automation->CompareElements(edit,active.Get(),&equal))&&equal;
}
inline bool countMask(IUIAutomation* automation,IUIAutomationElement* edit,DWORD pid,unsigned& count)
{
    // Read only advertised masked text. A buggy raw value is wiped, never logged,
    // and rejected before another gesture or capture. Some native password Edit
    // providers report an empty TextPattern irrespective of their native length.
    bool emptyReadable=false;Text value;ComPtr<IUIAutomationTextPattern> textPattern;ComPtr<IUIAutomationTextRange> range;
    if(SUCCEEDED(edit->GetCurrentPatternAs(UIA_TextPatternId,IID_PPV_ARGS(&textPattern)))&&textPattern
       &&SUCCEEDED(textPattern->get_DocumentRange(&range))&&range&&SUCCEEDED(range->GetText(129,&value.value))){
        const UINT n=value.value?SysStringLen(value.value):0;if(n>128)return false;
        for(UINT i=0;i<n;++i)if(value.value[i]!=L'\x2022')return false;
        if(n){count=n;return true;}emptyReadable=true;
    }
    auto readableEmpty=[&](){if(emptyReadable)count=0;return emptyReadable;};
    // Qualification harness/native Edit only: owner/type/element identity,
    // native password glyph and WM_GETTEXTLENGTH prove the masked count without
    // reading WM_GETTEXT. QML windows cannot take this fallback.
    UIA_HWND raw{};if(FAILED(edit->get_CurrentNativeWindowHandle(&raw)))return readableEmpty();
    HWND native=reinterpret_cast<HWND>(raw);wchar_t className[32]{};DWORD nativePid=0;
    if(!native||GetWindowThreadProcessId(native,&nativePid)==0||nativePid!=pid||!GetClassNameW(native,className,32)||wcscmp(className,L"Edit")!=0)return readableEmpty();
    ComPtr<IUIAutomationElement> nativeElement;BOOL equal=FALSE;
    if(FAILED(automation->ElementFromHandle(native,&nativeElement))||!nativeElement
       ||FAILED(automation->CompareElements(edit,nativeElement.Get(),&equal))||!equal)return false;
    DWORD_PTR glyph=0,length=0;
    if(!SendMessageTimeoutW(native,EM_GETPASSWORDCHAR,0,0,SMTO_ABORTIFHUNG|SMTO_BLOCK,500,&glyph)||glyph!=0x2022
       ||!SendMessageTimeoutW(native,WM_GETTEXTLENGTH,0,0,SMTO_ABORTIFHUNG|SMTO_BLOCK,500,&length)||length>128)return false;
    count=static_cast<unsigned>(length);return true;
}
inline Result enter(IUIAutomation* automation,IUIAutomationElement* edit,DWORD pid,HANDLE process,HWND window,const std::wstring& tokenFile)
{
    ComPtr<IUIAutomation2> bounded;
    if(!automation||FAILED(automation->QueryInterface(IID_PPV_ARGS(&bounded)))||!bounded
       ||FAILED(bounded->put_ConnectionTimeout(800))||FAILED(bounded->put_TransactionTimeout(1000)))return failed(Stage::Target,ERROR_NOT_SUPPORTED);
    Secret secret;if(!readSecret(tokenFile,secret))return failed(Stage::File,ERROR_ACCESS_DENIED);
    if(!target(automation,edit,pid,process,window))return failed(Stage::Target,ERROR_ACCESS_DENIED);
    unsigned before=0;if(!countMask(automation,edit,pid,before)||before!=0)return failed(Stage::Empty,ERROR_INVALID_DATA);
    InputBuffer inputs;inputs.data.reserve(86);
    for(unsigned i=0;i<43;++i){INPUT key{};key.type=INPUT_KEYBOARD;key.ki.wScan=static_cast<unsigned char>(secret.bytes[i]);key.ki.dwFlags=KEYEVENTF_UNICODE;inputs.data.push_back(key);key.ki.dwFlags|=KEYEVENTF_KEYUP;inputs.data.push_back(key);}
    if(!target(automation,edit,pid,process,window))return failed(Stage::Target,ERROR_ACCESS_DENIED);
    unsigned checked=0;if(!countMask(automation,edit,pid,checked)||checked!=0)return failed(Stage::Empty,ERROR_INVALID_DATA);
    // SendInput is not atomically PID-addressed. Re-sample ownership/focus
    // immediately before insertion; any partial insertion ends the attempt.
    if(!target(automation,edit,pid,process,window))return failed(Stage::Target,ERROR_ACCESS_DENIED);
    Result result;result.stage=Stage::Input;SetLastError(ERROR_SUCCESS);
    result.inputCount=SendInput(static_cast<UINT>(inputs.data.size()),inputs.data.data(),sizeof(INPUT));
    if(result.inputCount!=inputs.data.size()){result.error=GetLastError();if(!result.error)result.error=ERROR_WRITE_FAULT;return result;}
    // Only a small bounded masked-count observation is retried; no extra input.
    result.stage=Stage::Mask;
    for(unsigned tries=0;tries<10;++tries){
        if(!target(automation,edit,pid,process,window)){result.error=ERROR_ACCESS_DENIED;return result;}
        unsigned n=0;if(!countMask(automation,edit,pid,n)){result.error=ERROR_INVALID_DATA;return result;}
        if(n==43){result.passed=true;result.maskedLength=n;result.stage=Stage::Complete;return result;}
        if(n>43){result.error=ERROR_INVALID_DATA;return result;}Sleep(30);
    }
    result.error=ERROR_TIMEOUT;return result;
}
}
