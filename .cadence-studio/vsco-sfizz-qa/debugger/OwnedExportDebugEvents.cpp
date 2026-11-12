// SPDX-License-Identifier: GPL-3.0-only
// Launch only our pinned-Cadence export in disposable native Windows CI.
// Output contains debug events/module names+offsets/RIP, never memory or dumps.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
struct Handle {
    HANDLE value = nullptr;
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle() = default;
    explicit Handle(HANDLE h) : value(h) {}
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};
struct Attributes {
    std::vector<unsigned char> memory;
    LPPROC_THREAD_ATTRIBUTE_LIST list = nullptr;
    ~Attributes() { if (list) DeleteProcThreadAttributeList(list); }
};
void duplicateStandard(HANDLE& destination,DWORD key,DWORD access) {
    HANDLE source = GetStdHandle(key);
    if (source && source != INVALID_HANDLE_VALUE) {
        if (!DuplicateHandle(GetCurrentProcess(),source,GetCurrentProcess(),&destination,0,TRUE,DUPLICATE_SAME_ACCESS)) throw std::runtime_error("Cannot duplicate owned standard handle");
    } else {
        SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES),nullptr,TRUE};
        destination=CreateFileW(L"NUL",access,FILE_SHARE_READ|FILE_SHARE_WRITE,&security,OPEN_EXISTING,0,nullptr);
        if (destination==INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot open owned NUL stream");
    }
}
std::wstring envValue(const wchar_t* name) {
    DWORD size = GetEnvironmentVariableW(name, nullptr, 0);
    if (!size) return {};
    std::vector<wchar_t> buffer(size);
    DWORD actual = GetEnvironmentVariableW(name, buffer.data(), size);
    if (!actual || actual >= size) throw std::runtime_error("Environment variable read failed");
    return std::wstring(buffer.data(), actual);
}
bool same(const fs::path& a, const fs::path& b) { return _wcsicmp(a.c_str(), b.c_str()) == 0; }
bool strictlyBelow(const fs::path& value, const fs::path& root) {
    auto a = value.begin(); auto b = root.begin();
    for (; b != root.end(); ++a, ++b) if (a == value.end() || !same(*a, *b)) return false;
    return a != value.end();
}
std::string utf8(const std::wstring& value) {
    if (value.empty()) return {};
    int count = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    if (!count) throw std::runtime_error("Invalid UTF16 module name");
    std::string result(static_cast<size_t>(count), '\0');
    if (WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), result.data(), count, nullptr, nullptr) != count)
        throw std::runtime_error("UTF8 module-name conversion failed");
    return result;
}
std::string jsonString(const std::string& value) {
    std::string result = "\""; const char* digits = "0123456789abcdef";
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') { result += '\\'; result += static_cast<char>(c); }
        else if (c < 32) { result += "\\u00"; result += digits[c >> 4]; result += digits[c & 15]; }
        else result += static_cast<char>(c);
    }
    return result + '"';
}
std::string hex(std::uint64_t value) { std::ostringstream out; out << "0x" << std::hex << value; return out.str(); }
std::wstring quote(const std::wstring& value) {
    std::wstring result = L"\""; size_t slashes = 0;
    for (wchar_t c : value) {
        if (c == L'\\') { ++slashes; continue; }
        if (c == L'"') result.append(slashes * 2 + 1, L'\\'); else result.append(slashes, L'\\');
        result += c; slashes = 0;
    }
    result.append(slashes * 2, L'\\'); return result + L'"';
}
std::vector<wchar_t> childEnvironment(const fs::path& executable) {
    const wchar_t* allowed[] = {L"ALLUSERSPROFILE",L"APPDATA",L"COMSPEC",L"CommonProgramFiles",L"CommonProgramFiles(x86)",
        L"HOMEDRIVE",L"HOMEPATH",L"LOCALAPPDATA",L"NUMBER_OF_PROCESSORS",L"OS",L"PROCESSOR_ARCHITECTURE",L"ProgramData",
        L"ProgramFiles",L"ProgramFiles(x86)",L"PUBLIC",L"SystemDrive",L"SystemRoot",L"TEMP",L"TMP",L"USERPROFILE",L"windir"};
    struct Less { bool operator()(const std::wstring& a,const std::wstring& b) const { return _wcsicmp(a.c_str(),b.c_str()) < 0; } };
    std::map<std::wstring,std::wstring,Less> values;
    for (const auto* key : allowed) { auto value = envValue(key); if (!value.empty()) values.emplace(key,value); }
    auto systemRoot = envValue(L"SystemRoot"); if (systemRoot.empty()) throw std::runtime_error("SystemRoot is required");
    values[L"PATH"] = executable.parent_path().wstring() + L";" + (fs::path(systemRoot)/L"System32").wstring();
    std::vector<wchar_t> result;
    for (const auto& pair : values) { auto entry = pair.first + L"=" + pair.second; result.insert(result.end(),entry.begin(),entry.end()); result.push_back(L'\0'); }
    result.push_back(L'\0'); return result;
}
struct Module { std::uintptr_t base = 0; DWORD size = 0; std::string name; bool loaded = true; };
std::string basenameFromFile(HANDLE file) {
    if (!file || file == INVALID_HANDLE_VALUE) return "unknown";
    std::vector<wchar_t> name(32768); DWORD count = GetFinalPathNameByHandleW(file,name.data(),static_cast<DWORD>(name.size()),FILE_NAME_NORMALIZED);
    if (!count || count >= name.size()) return "unknown";
    return utf8(fs::path(std::wstring(name.data(),count)).filename().wstring());
}
DWORD imageSize(HANDLE process, std::uintptr_t base) {
    // Bounded PE-header reads only, never stack/heap/environment memory.
    IMAGE_DOS_HEADER dos{}; SIZE_T read = 0;
    if (!ReadProcessMemory(process,reinterpret_cast<LPCVOID>(base),&dos,sizeof(dos),&read) || read != sizeof(dos) || dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew < 0 || dos.e_lfanew > 1048576) return 0;
    IMAGE_NT_HEADERS64 nt{};
    if (!ReadProcessMemory(process,reinterpret_cast<LPCVOID>(base + static_cast<std::uintptr_t>(dos.e_lfanew)),&nt,sizeof(nt),&read) || read != sizeof(nt) || nt.Signature != IMAGE_NT_SIGNATURE || nt.FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64 || nt.OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return 0;
    return nt.OptionalHeader.SizeOfImage;
}
std::string location(const std::vector<Module>& modules, std::uintptr_t address) {
    for (bool loaded : {true,false}) for (auto it = modules.rbegin(); it != modules.rend(); ++it) {
        if (it->loaded == loaded && address >= it->base && address - it->base < it->size)
            return "\"module\":" + jsonString(it->name) + ",\"module_state\":" + jsonString(loaded ? "loaded" : "unloaded") + ",\"module_offset\":" + jsonString(hex(address-it->base));
    }
    return "\"module\":null,\"module_state\":\"unknown\",\"module_offset\":null";
}
int wmain(int argc,wchar_t** argv) {
    PROCESS_INFORMATION child{}; Handle output; bool childStarted = false; unsigned eventCount = 0;
    auto emit = [&](const std::string& text) {
        if (!output.value || ++eventCount > 1024) throw std::runtime_error("Owned event log is unavailable or exceeds its bound");
        const auto line = text + "\n"; DWORD written = 0;
        if (!WriteFile(output.value,line.data(),static_cast<DWORD>(line.size()),&written,nullptr) || written != line.size()) throw std::runtime_error("Event write failed");
    };
    try {
        if (argc != 6 || sizeof(void*) != 8 || envValue(L"GITHUB_ACTIONS") != L"true" || envValue(L"CI") != L"true" || envValue(L"RUNNER_ENVIRONMENT") != L"github-hosted")
            throw std::runtime_error("Only a single owned native Windows x64 hosted-CI export is supported");
        const auto temporary = fs::canonical(fs::path(envValue(L"RUNNER_TEMP")));
        const auto executable = fs::canonical(fs::path(argv[1])); const auto working = fs::canonical(fs::path(argv[2]));
        const auto eventPath = fs::weakly_canonical(fs::path(argv[3])); const auto wav = fs::weakly_canonical(fs::path(argv[4])); const auto score = fs::canonical(fs::path(argv[5]));
        for (const auto& path : {executable,working,eventPath,wav,score}) if (!strictlyBelow(path,temporary)) throw std::runtime_error("All export paths must be strictly below RUNNER_TEMP");
        if (!same(executable.filename(),L"CadenceStudio4.exe") || !same(eventPath.extension(),L".jsonl") || !same(wav.extension(),L".wav") || !same(score.extension(),L".mscz") ||
            !same(eventPath.parent_path(),working) || !same(wav.parent_path(),working) || !same(score.parent_path(),working) || fs::exists(eventPath) || fs::exists(wav) || !fs::is_regular_file(score))
            throw std::runtime_error("Only new event/WAV outputs and an existing controlled native-score copy are allowed");
        output.value = CreateFileW(eventPath.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
        if (output.value == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot exclusively create event log");
        auto environment = childEnvironment(executable);
        auto command = quote(executable.wstring()) + L" -o " + quote(wav.wstring()) + L" " + quote(score.wstring());
        Handle standardIn,standardOut,standardErr;
        duplicateStandard(standardIn.value,STD_INPUT_HANDLE,GENERIC_READ);
        duplicateStandard(standardOut.value,STD_OUTPUT_HANDLE,GENERIC_WRITE);
        duplicateStandard(standardErr.value,STD_ERROR_HANDLE,GENERIC_WRITE);
        HANDLE inherited[] = {standardIn.value,standardOut.value,standardErr.value};
        SIZE_T attributeBytes=0; InitializeProcThreadAttributeList(nullptr,1,0,&attributeBytes);
        if (!attributeBytes) throw std::runtime_error("Cannot size explicit handle allowlist");
        Attributes attributes;attributes.memory.resize(attributeBytes);
        auto* list=reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attributes.memory.data());
        if (!InitializeProcThreadAttributeList(list,1,0,&attributeBytes)) throw std::runtime_error("Cannot initialize handle allowlist");
        attributes.list=list;
        if (!UpdateProcThreadAttribute(list,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,inherited,sizeof(inherited),nullptr,nullptr)) throw std::runtime_error("Cannot set handle allowlist");
        STARTUPINFOEXW startup{};startup.StartupInfo.cb=sizeof(startup);startup.StartupInfo.dwFlags=STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput=standardIn.value;startup.StartupInfo.hStdOutput=standardOut.value;startup.StartupInfo.hStdError=standardErr.value;startup.lpAttributeList=list;
        if (!CreateProcessW(executable.c_str(),command.data(),nullptr,nullptr,TRUE,DEBUG_ONLY_THIS_PROCESS|CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW|EXTENDED_STARTUPINFO_PRESENT,environment.data(),working.c_str(),&startup.StartupInfo,&child))
            throw std::runtime_error("Cannot create the owned export process");
        childStarted = true; if (!DebugSetProcessKillOnExit(TRUE)) throw std::runtime_error("Cannot constrain owned-child debugger lifetime");
        emit("{\"event\":\"owned_process_started\",\"pid\":"+std::to_string(child.dwProcessId)+",\"debug_only_this_process\":true,\"environment_allowlist\":true,\"memory_dump_created\":false,\"data_memory_captured\":false}");
        const auto started = GetTickCount64(); std::vector<Module> modules; bool initialBreakpointHandled = false;
        while (true) {
            if (GetTickCount64()-started > 85000) {
                const bool requested=TerminateProcess(child.hProcess,124)!=FALSE;
                const bool observed=WaitForSingleObject(child.hProcess,5000)==WAIT_OBJECT_0;
                emit("{\"event\":\"owned_process_timeout\",\"termination_request_succeeded\":"+std::string(requested?"true":"false")+",\"exit_observed_within_5s\":"+(observed?"true":"false")+"}");
                CloseHandle(child.hThread);CloseHandle(child.hProcess);return 124;
            }
            DEBUG_EVENT event{};
            if (!WaitForDebugEvent(&event,100)) { if (GetLastError()==ERROR_SEM_TIMEOUT) continue; throw std::runtime_error("WaitForDebugEvent failed"); }
            if (event.dwProcessId != child.dwProcessId) throw std::runtime_error("Unexpected process debug event");
            DWORD continuation = DBG_CONTINUE;
            if (event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT || event.dwDebugEventCode == LOAD_DLL_DEBUG_EVENT) {
                const bool main = event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT;
                HANDLE file = main ? event.u.CreateProcessInfo.hFile : event.u.LoadDll.hFile;
                auto base = reinterpret_cast<std::uintptr_t>(main ? event.u.CreateProcessInfo.lpBaseOfImage : event.u.LoadDll.lpBaseOfDll);
                Module module{base,imageSize(child.hProcess,base),basenameFromFile(file),true}; modules.push_back(module);
                if (file && file!=INVALID_HANDLE_VALUE) CloseHandle(file);
                emit("{\"event\":\"module_loaded\",\"module\":"+jsonString(module.name)+",\"base\":"+jsonString(hex(base))+",\"image_bytes\":"+std::to_string(module.size)+"}");
            } else if (event.dwDebugEventCode == UNLOAD_DLL_DEBUG_EVENT) {
                auto base = reinterpret_cast<std::uintptr_t>(event.u.UnloadDll.lpBaseOfDll);
                for (auto it=modules.rbegin();it!=modules.rend();++it) if (it->base==base && it->loaded) { it->loaded=false; break; }
                emit("{\"event\":\"module_unloaded\",\"base\":"+jsonString(hex(base))+"}");
            } else if (event.dwDebugEventCode == EXCEPTION_DEBUG_EVENT) {
                const auto& info = event.u.Exception; auto code = info.ExceptionRecord.ExceptionCode;
                auto address=reinterpret_cast<std::uintptr_t>(info.ExceptionRecord.ExceptionAddress);
                bool knownModule=false,loaderModule=false;
                for (auto it=modules.rbegin();it!=modules.rend();++it) if (it->loaded && address>=it->base && address-it->base<it->size) {
                    knownModule=true;loaderModule=_stricmp(it->name.c_str(),"ntdll.dll")==0;break;
                }
                if (code==EXCEPTION_BREAKPOINT && !initialBreakpointHandled && info.dwFirstChance && event.dwThreadId==child.dwThreadId && (!knownModule || loaderModule)) {
                    initialBreakpointHandled=true;
                    emit("{\"event\":\"initial_loader_breakpoint\",\"thread_id\":"+std::to_string(event.dwThreadId)+",\"first_chance\":true,\"module_identified\":"+(knownModule?"true":"false")+","+location(modules,address)+"}");
                }
                else {
                    continuation=DBG_EXCEPTION_NOT_HANDLED;
                    if (code==EXCEPTION_ACCESS_VIOLATION || code==EXCEPTION_ILLEGAL_INSTRUCTION || code==EXCEPTION_STACK_OVERFLOW || code==EXCEPTION_IN_PAGE_ERROR ||
                        code==0xC0000409UL || code==0xC0000374UL || code==0xC0000602UL || code==0xC0000417UL || code==0x40000015UL || code==EXCEPTION_BREAKPOINT) {
                        // STATUS_STACK_BUFFER_OVERRUN carries a documented FAST_FAIL
                        // reason in parameter0. Emit only a bounded small identifier,
                        // never arbitrary exception arguments or addresses/data.
                        std::string fastFailCode="null";
                        if (code==0xC0000409UL && info.ExceptionRecord.NumberParameters>=1 && info.ExceptionRecord.ExceptionInformation[0]<=65535)
                            fastFailCode=std::to_string(static_cast<unsigned>(info.ExceptionRecord.ExceptionInformation[0]));
                        std::string context="null"; Handle thread(OpenThread(THREAD_GET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,event.dwThreadId));
                        CONTEXT registers{};registers.ContextFlags=CONTEXT_CONTROL;
                        if (thread.value && GetThreadContext(thread.value,&registers)) context=jsonString(hex(registers.Rip));
                        emit("{\"event\":\"exception\",\"thread_id\":"+std::to_string(event.dwThreadId)+",\"code\":"+jsonString(hex(code))+",\"first_chance\":"+(info.dwFirstChance?"true":"false")+",\"instruction_pointer\":"+jsonString(hex(address))+",\"context_RIP\":"+context+",\"fast_fail_code\":"+fastFailCode+","+location(modules,address)+"}");
                    }
                }
            } else if (event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT) {
                const auto code=event.u.ExitProcess.dwExitCode;
                emit("{\"event\":\"owned_process_exit\",\"pid\":"+std::to_string(child.dwProcessId)+",\"exit_code\":"+std::to_string(code)+"}");
                ContinueDebugEvent(event.dwProcessId,event.dwThreadId,DBG_CONTINUE);
                CloseHandle(child.hThread);CloseHandle(child.hProcess);return static_cast<int>(code);
            }
            if (!ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation)) throw std::runtime_error("ContinueDebugEvent failed");
        }
    } catch (const std::exception&) {
        // No exception text/environment/path is emitted. This is a tool failure.
        if (output.value && output.value!=INVALID_HANDLE_VALUE) { const char line[]="{\"event\":\"debugger_tool_failed\"}\n";DWORD written=0;WriteFile(output.value,line,sizeof(line)-1,&written,nullptr); }
        if (childStarted) { TerminateProcess(child.hProcess,125);WaitForSingleObject(child.hProcess,5000);CloseHandle(child.hThread);CloseHandle(child.hProcess); }
        return 125;
    }
}
