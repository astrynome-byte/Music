// SPDX-License-Identifier: GPL-3.0-only
// Inspect and invoke only semantic controls of the PID supplied by our launcher.
#define NOMINMAX
#include <windows.h>
#include <UIAutomation.h>
#include <wrl/client.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cwchar>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "OwnedScoreKeyboard.h"
#include "ObservationGraph.h"

using Microsoft::WRL::ComPtr;
using Clock = std::chrono::steady_clock;
static DWORD targetPid = 0;
static HANDLE targetProcess = nullptr;
static Clock::time_point deadline;
static std::vector<std::string> actions;
static std::vector<std::string> keyboardFrames;
static int keyboardGestureAttempts = 0;
static int scoreNavigationAttempts = 0;
static std::vector<std::string> focusEvidence;
static int f6GestureAttempts = 0, tabGestureAttempts = 0, rightGestureAttempts = 0, leftGestureAttempts = 0, downGestureAttempts = 0, returnGestureAttempts = 0;
static bool keyboardFailure = false;
static int endGestureAttempts = 0;
static bool diagnosticTreeIncomplete = false;
using cadence_observation::RuntimeId;
struct SnapshotState {
    bool incomplete = false, runtimeIdentityUnknown = false, foreignNodeObserved = false;
    HRESULT failure = S_OK;
    std::string operation;
    void fail(const char* name, HRESULT hr) {
        incomplete = true; diagnosticTreeIncomplete = true;
        if (operation.empty()) { operation = name; failure = hr; }
    }
};

static std::string utf8(const std::wstring& value)
{
    if (value.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string out(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), out.data(), n, nullptr, nullptr);
    return out;
}
static std::string jsonQuoted(const std::wstring& value)
{
    std::string out = "\"";
    for (unsigned char c : utf8(value)) {
        if (c == '\\' || c == '"') { out += '\\'; out += static_cast<char>(c); }
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c < 32) out += "?";
        else out += static_cast<char>(c);
    }
    return out + "\"";
}
static std::wstring text(BSTR value)
{
    std::wstring out = value ? std::wstring(value, std::min<UINT>(SysStringLen(value), 512)) : L"";
    SysFreeString(value);
    return out;
}
static bool alive()
{
    DWORD exitCode = 0;
    return targetProcess && GetExitCodeProcess(targetProcess, &exitCode) && exitCode == STILL_ACTIVE;
}
static bool owned(HWND window)
{
    DWORD pid = 0;
    return alive() && window && GetWindowThreadProcessId(window, &pid) != 0 && pid == targetPid;
}
static std::vector<HWND> windows()
{
    std::vector<HWND> result;
    EnumWindows([](HWND window, LPARAM data) -> BOOL {
        if (owned(window) && IsWindowVisible(window)) reinterpret_cast<std::vector<HWND>*>(data)->push_back(window);
        return TRUE;
    }, reinterpret_cast<LPARAM>(&result));
    return result;
}
static std::wstring windowTitle(HWND window)
{
    wchar_t value[513] = {};
    GetWindowTextW(window, value, 513);
    return value;
}
static HWND mainWindow()
{
    HWND best = nullptr;
    long long area = -1;
    for (HWND window : windows()) {
        if (GetWindow(window, GW_OWNER)) continue;
        RECT rect = {};
        if (!GetWindowRect(window, &rect)) continue;
        long long candidate = static_cast<long long>(rect.right - rect.left) * (rect.bottom - rect.top);
        if (candidate > area) { best = window; area = candidate; }
    }
    return best;
}
static bool closeIntroductionOnly()
{
    bool posted = false;
    for (HWND window : windows()) {
        const std::wstring title = windowTitle(window);
        HWND owner = GetWindow(window, GW_OWNER);
        if (title.find(L"Introduction") == std::wstring::npos || !owned(owner) || IsWindowEnabled(owner)) continue;
        // Recheck the exact process immediately before the only posted message.
        bool ok = owned(window) && owned(owner) && PostMessageW(window, WM_CLOSE, 0, 0);
        actions.push_back("{\"action\":\"close_owned_introduction_only\",\"title\":" + jsonQuoted(title)
                          + ",\"pid\":" + std::to_string(targetPid) + ",\"posted\":" + (ok ? "true" : "false") + "}");
        posted = posted || ok;
    }
    return posted;
}

struct Node {
    ComPtr<IUIAutomationElement> element;
    RuntimeId runtimeId;
    std::wstring name, id;
    int pid = 0, type = 0, depth = 0;
    BOOL enabled = FALSE, offscreen = TRUE, focused = FALSE;
};
static std::wstring controlLabel(const std::wstring& name)
{
    // MuseScore's accessible Name prepends the current panel to its focused
    // control (AccessibleItemInterface::text). Strip only known source labels.
    const std::vector<std::wstring> prefixes {
        L"Panneau Menu Application, ", L"Menu Application panel, ", L"Application menu panel, ",
        L"Panneau LocalScoreRecognition, ", L"LocalScoreRecognition panel, ",
        L"Panneau LocalAudioTranscriptionControls, ", L"LocalAudioTranscriptionControls panel, ",
        L"Panneau Fichier, ", L"Fichier panel, ", L"File panel, ", L"Panneau File, ",
        L"Panneau Notes priv\u00e9es de pratique, ", L"Panneau Partitions, ", L"Scores panel, ",
        L"Panneau Barre d'onglets des partitions, ", L"Scores tab bar panel, ",
        L"Panneau Biblioth\u00e8que locale, ", L"Biblioth\u00e8que locale panel, ", L"Local library panel, ", L"Panneau Dropdown, ", L"Dropdown panel, "
    };
    for (const auto& prefix : prefixes) if (name.rfind(prefix, 0) == 0) return name.substr(prefix.size());
    return name;
}
static Node focusedNode(IUIAutomation* automation)
{
    Node node;
    if (SUCCEEDED(automation->GetFocusedElement(&node.element)) && node.element) {
        BSTR name = nullptr;
        node.element->get_CurrentName(&name); node.name = text(name);
        node.element->get_CurrentProcessId(&node.pid); node.element->get_CurrentControlType(&node.type);
        node.element->get_CurrentIsEnabled(&node.enabled); node.element->get_CurrentIsOffscreen(&node.offscreen);
        node.element->get_CurrentHasKeyboardFocus(&node.focused);
    }
    return node;
}
static RuntimeId runtimeIdentity(IUIAutomationElement* element, SnapshotState& state)
{
    // Reuse the bounded RuntimeId reader from the v3/f10 observation client.
    // Scope is checked before identity lookup, including for repeated nodes.
    int pid = 0;
    const HRESULT processResult = element ? element->get_CurrentProcessId(&pid) : E_POINTER;
    if (FAILED(processResult) || pid != static_cast<int>(targetPid)) {
        state.foreignNodeObserved = true;
        state.fail("runtimeIdentity.process_scope", FAILED(processResult) ? processResult : E_ACCESSDENIED); return {};
    }
    SAFEARRAY* raw = nullptr;
    const HRESULT fetched = element->GetRuntimeId(&raw);
    struct ArrayOwner { SAFEARRAY* value; ~ArrayOwner() { if (value) SafeArrayDestroy(value); } } owner {raw};
    LONG first = 0, last = -1;
    VARTYPE kind = VT_EMPTY;
    if (FAILED(fetched) || !raw || SafeArrayGetDim(raw) != 1
        || SafeArrayGetElemsize(raw) != sizeof(int)
        || FAILED(SafeArrayGetVartype(raw,&kind)) || kind != VT_I4
        || FAILED(SafeArrayGetLBound(raw,1,&first)) || FAILED(SafeArrayGetUBound(raw,1,&last))
        || last < first || static_cast<long long>(last) - static_cast<long long>(first) + 1 > cadence_observation::Graph::maxIdParts) {
        state.runtimeIdentityUnknown = true;
        state.fail("runtimeIdentity.GetRuntimeId_or_SAFEARRAY_shape", FAILED(fetched) ? fetched : E_INVALIDARG); return {};
    }
    RuntimeId id;
    for (LONG index = first; index <= last; ++index) {
        int part = 0;
        const HRESULT readPart = SafeArrayGetElement(raw,&index,&part);
        if (FAILED(readPart)) {
            state.runtimeIdentityUnknown = true;
            state.fail("runtimeIdentity.SafeArrayGetElement",readPart); return {};
        }
        id.push_back(part);
        if (index == last) break;
    }
    return id;
}
static std::string runtimeJson(const RuntimeId& id)
{
    std::string out = "[";
    for (size_t i = 0; i < id.size(); ++i) { if (i) out += ','; out += std::to_string(id[i]); }
    return out + ']';
}
static void walk(IUIAutomationTreeWalker* walker, IUIAutomationElement* element, const RuntimeId& id,
                 int depth, std::vector<Node>& nodes, cadence_observation::Graph& graph,
                 SnapshotState& state, const RuntimeId& parent, const std::string& relation)
{
    if (state.incomplete) return;
    if (Clock::now() > deadline || !alive()) { state.fail("walk.deadline_or_process_exit",E_ABORT); return; }
    Node node;
    node.element = element; node.runtimeId = id; node.depth = depth;
    const HRESULT processResult = element ? element->get_CurrentProcessId(&node.pid) : E_POINTER;
    if (FAILED(processResult) || node.pid != static_cast<int>(targetPid)) {
        state.foreignNodeObserved = true;
        state.fail("walk.process_scope",FAILED(processResult) ? processResult : E_ACCESSDENIED); return;
    }
    // Do not skip a duplicate until its current PID has been validated.
    const auto visit = graph.enter(id,parent,relation);
    if (visit == cadence_observation::Visit::cycle) {
        state.fail("walk.provider_cycle",E_FAIL); return;
    }
    if (visit == cadence_observation::Visit::duplicate) return;
    if (visit != cadence_observation::Visit::first || depth > 18) {
        state.fail(depth > 18 ? "walk.depth_limit" : "walk.identity_or_graph_limit",E_FAIL); return;
    }
    cadence_observation::ActiveScope leave(graph,id);
    BSTR name = nullptr, automationId = nullptr;
    const HRESULT named = element->get_CurrentName(&name); node.name = text(name);
    const HRESULT identified = element->get_CurrentAutomationId(&automationId); node.id = text(automationId);
    const HRESULT typed = element->get_CurrentControlType(&node.type);
    const HRESULT enabled = element->get_CurrentIsEnabled(&node.enabled);
    const HRESULT offscreen = element->get_CurrentIsOffscreen(&node.offscreen);
    const HRESULT focused = element->get_CurrentHasKeyboardFocus(&node.focused);
    if (FAILED(named) || FAILED(identified) || FAILED(typed) || FAILED(enabled) || FAILED(offscreen) || FAILED(focused)) {
        state.fail("walk.node_property",FAILED(named) ? named : FAILED(identified) ? identified : FAILED(typed) ? typed
                   : FAILED(enabled) ? enabled : FAILED(offscreen) ? offscreen : focused); return;
    }
    nodes.push_back(node);
    ComPtr<IUIAutomationElement> child;
    const HRESULT firstChildResult = walker->GetFirstChildElement(element,&child);
    if (FAILED(firstChildResult)) { state.fail("walk.GetFirstChildElement",firstChildResult); return; }
    std::set<RuntimeId> siblings;
    std::string edge = "first_child";
    RuntimeId edgeSource = id;
    while (child && Clock::now() <= deadline && alive() && !state.incomplete) {
        const auto childId = runtimeIdentity(child.Get(),state);
        if (childId.empty()) break;
        if (!siblings.insert(childId).second) {
            if (!graph.siblingRepeat(edgeSource,childId)) state.fail("walk.sibling_edge_limit",E_FAIL);
            else state.fail("walk.provider_repeated_sibling",E_FAIL);
            break;
        }
        walk(walker,child.Get(),childId,depth+1,nodes,graph,state,edgeSource,edge);
        if (state.incomplete) break;
        ComPtr<IUIAutomationElement> sibling;
        const HRESULT nextSiblingResult = walker->GetNextSiblingElement(child.Get(),&sibling);
        if (FAILED(nextSiblingResult)) { state.fail("walk.GetNextSiblingElement",nextSiblingResult); break; }
        edgeSource = childId; child = sibling; edge = "next_sibling";
    }
    if (Clock::now() > deadline || !alive()) state.fail("walk.deadline_or_process_exit",E_ABORT);
}
static std::vector<Node> snapshot(IUIAutomation* automation, const std::filesystem::path& output, const wchar_t* phase)
{
    std::vector<Node> nodes;
    SnapshotState state;
    cadence_observation::Graph graph;
    std::vector<std::string> inspectedWindows;
    ComPtr<IUIAutomationTreeWalker> walker;
    const HRESULT walkerResult = automation->get_RawViewWalker(&walker);
    if (FAILED(walkerResult) || !walker) state.fail("snapshot.RawViewWalker",FAILED(walkerResult) ? walkerResult : E_POINTER);
    if (SUCCEEDED(walkerResult) && walker) {
        for (HWND window : windows()) {
            if (state.incomplete) break;
            ComPtr<IUIAutomationElement> element;
            if (!owned(window)) continue;
            const HRESULT elementResult = automation->ElementFromHandle(window, &element);
            inspectedWindows.push_back("{\"handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(window))
                                       + ",\"title\":" + jsonQuoted(windowTitle(window))
                                       + ",\"pid\":" + std::to_string(targetPid)
                                       + ",\"enabled\":" + (IsWindowEnabled(window) ? "true" : "false")
                                       + ",\"owner_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(GetWindow(window, GW_OWNER)))
                                       + ",\"element_from_handle_hresult\":" + std::to_string(static_cast<long>(elementResult)) + '}');
            if (FAILED(elementResult)) state.fail("snapshot.ElementFromHandle",elementResult);
            else {
                const auto id = runtimeIdentity(element.Get(),state);
                if (!id.empty()) walk(walker.Get(),element.Get(),id,0,nodes,graph,state,{},"owned_window");
            }
        }
    }
    if (nodes.empty()) state.fail("snapshot.no_owned_nodes",E_FAIL);
    if (nodes.size() >= 1200) state.fail("snapshot.node_limit",E_FAIL);
    if (Clock::now() > deadline || !alive()) state.fail("snapshot.deadline_or_process_exit",E_ABORT);
    std::ofstream file(output / (std::wstring(phase) + L".json"), std::ios::binary);
    file << "{\"pid\":" << targetPid << ",\"bounded\":true,\"max_nodes\":1200,\"max_depth\":18,\"deadline_reached\":"
         << (Clock::now() > deadline ? "true" : "false") << ",\"node_limit_reached\":" << (nodes.size() >= 1200 ? "true" : "false") << ",\"nodes\":[";
    bool first = true;
    for (const Node& node : nodes) {
        if (!first) file << ',';
        first = false;
        file << "{\"name\":" << jsonQuoted(node.name) << ",\"automation_id\":" << jsonQuoted(node.id)
             << ",\"runtime_id\":" << runtimeJson(node.runtimeId)
             << ",\"control_type\":" << node.type << ",\"pid\":" << node.pid << ",\"depth\":" << node.depth
             << ",\"enabled\":" << (node.enabled ? "true" : "false") << ",\"offscreen\":" << (node.offscreen ? "true" : "false")
             << ",\"keyboard_focus\":" << (node.focused ? "true" : "false") << '}';
    }
    file << "],\"walker_hresult\":" << static_cast<long>(walkerResult) << ",\"inspected_windows\":[";
    for (size_t i = 0; i < inspectedWindows.size(); ++i) { if (i) file << ','; file << inspectedWindows[i]; }
    file << "],\"tree_incomplete\":" << (state.incomplete ? "true" : "false")
         << ",\"phase_observation_incomplete\":" << (diagnosticTreeIncomplete ? "true" : "false")
         << ",\"runtime_identity_unknown\":" << (state.runtimeIdentityUnknown ? "true" : "false")
         << ",\"foreign_node_refused\":" << (state.foreignNodeObserved ? "true" : "false")
         << ",\"first_failure_operation\":" << jsonQuoted(std::wstring(state.operation.begin(),state.operation.end()))
         << ",\"first_failure_hresult\":" << static_cast<long>(state.failure)
         << ",\"unique_runtime_ids\":" << graph.uniqueNodes() << ",\"cycle_edges\":" << graph.cycleEdges
         << ",\"duplicate_edges\":" << graph.duplicateEdges << ",\"max_edges\":3600,\"graph_edges\":[";
    for (size_t i = 0; i < graph.edges.size(); ++i) {
        if (i) file << ',';
        const auto& edge = graph.edges[i];
        file << "{\"from\":" << runtimeJson(edge.from) << ",\"to\":" << runtimeJson(edge.to)
             << ",\"relation\":" << jsonQuoted(std::wstring(edge.relation.begin(),edge.relation.end()))
             << ",\"cycle\":" << (edge.cycle ? "true" : "false")
             << ",\"duplicate\":" << (edge.duplicate ? "true" : "false") << '}';
    }
    file << "]}";
    // Preserve diagnostic nodes on disk, but never use a partial projection
    // to select a semantic control or claim a complete GUI phase.
    if (state.incomplete) nodes.clear();
    return nodes;
}

static bool exactMainReady()
{
    const auto list=windows();HWND main=mainWindow();
    if (!owned(main) || !IsWindowEnabled(main) || list.size()!=1) return false;
    const auto title=windowTitle(main);
    return title.find(L"Cadence-QA-edit")!=std::wstring::npos;
}
static void diagnosticSnapshot(IUIAutomation* automation,const std::filesystem::path& output,const wchar_t* label)
{
    // Full Qt RawTree is diagnostic only. A failed unrelated getter/sibling does
    // not invalidate an independently proved focused-element ancestry.
    const auto phaseDeadline=deadline;
    deadline=std::min(phaseDeadline,Clock::now()+std::chrono::milliseconds(1500));
    snapshot(automation,output,label);deadline=phaseDeadline;
}
static bool liveScoreFocus(IUIAutomation* automation)
{
    if (!exactMainReady() || Clock::now()>=deadline) return false;
    const HWND main=mainWindow();
    OwnedKeyResult nativeFocus;
    // UIA can retain its last focused element after another process becomes
    // foreground. Require the live native focus and foreground to resolve to
    // this exact main window before accepting the semantic score context.
    if (!cadence_owned_keyboard_detail::sampleOwnedFocus(targetPid,nativeFocus)
        || !ExactScoreMainContext(main,nativeFocus)) return false;
    ComPtr<IUIAutomationElement> focused;
    HRESULT result=automation->GetFocusedElement(&focused);
    if (FAILED(result) || !focused) return false;
    int pid=0,type=0;BOOL enabled=FALSE,offscreen=TRUE,hasFocus=FALSE;
    if (FAILED(focused->get_CurrentProcessId(&pid)) || pid!=static_cast<int>(targetPid)
        || FAILED(focused->get_CurrentControlType(&type)) || type==UIA_EditControlTypeId
        || FAILED(focused->get_CurrentIsEnabled(&enabled)) || !enabled
        || FAILED(focused->get_CurrentIsOffscreen(&offscreen)) || offscreen
        || FAILED(focused->get_CurrentHasKeyboardFocus(&hasFocus)) || !hasFocus) return false;
    ComPtr<IUIAutomationTreeWalker> walker;
    if (FAILED(automation->get_RawViewWalker(&walker)) || !walker) return false;
    ComPtr<IUIAutomationElement> current=focused;
    std::set<RuntimeId> visited;std::string chain="[";
    for (int depth=0;current && depth<18 && Clock::now()<deadline;++depth) {
        SnapshotState state;auto id=runtimeIdentity(current.Get(),state);
        if (state.incomplete || id.empty() || !visited.insert(id).second) return false;
        BSTR raw=nullptr;result=current->get_CurrentName(&raw);auto name=text(raw);
        int currentType=0, currentPid=0;
        if (FAILED(result) || FAILED(current->get_CurrentControlType(&currentType))
            || FAILED(current->get_CurrentProcessId(&currentPid)) || currentPid!=static_cast<int>(targetPid)) return false;
        if(depth)chain+=',';
        chain+="{\"name\":"+jsonQuoted(name)+",\"control_type\":"+std::to_string(currentType)
            +",\"pid\":"+std::to_string(currentPid)+",\"runtime_id\":"+runtimeJson(id)+'}';
        // Source AccessibleRoot::accessibleName + role Panel, with one known
        // filename. Bare \"Score\" is the unrelated main toolbar radio too.
        if (name==L"Score Cadence-QA-edit" && currentType==UIA_PaneControlTypeId) {
            OwnedKeyResult rechecked;
            if (!exactMainReady()
                || !cadence_owned_keyboard_detail::sampleOwnedFocus(targetPid,rechecked)
                || rechecked.foreground!=nativeFocus.foreground || rechecked.focus!=nativeFocus.focus
                || !ExactScoreMainContext(main,rechecked)) return false;
            if(focusEvidence.size()<160)focusEvidence.push_back("{\"native_foreground_handle\":"
                +std::to_string(reinterpret_cast<std::uintptr_t>(rechecked.foreground))
                +",\"native_focus_handle\":"+std::to_string(reinterpret_cast<std::uintptr_t>(rechecked.focus))
                +",\"root_owner_handle\":"+std::to_string(reinterpret_cast<std::uintptr_t>(main))
                +",\"ancestors\":"+chain+']'+'}');
            return true;
        }
        ComPtr<IUIAutomationElement> parent;
        if (FAILED(walker->GetParentElement(current.Get(),&parent))) return false;
        current=parent;
    }
    return false;
}
static void recordInput(const char* action,const OwnedKeyResult& result)
{
    actions.push_back(std::string("{\"action\":\"")+action+"\",\"pid\":"+std::to_string(targetPid)
        +",\"foreground_handle\":"+std::to_string(reinterpret_cast<std::uintptr_t>(result.foreground))
        +",\"focus_handle\":"+std::to_string(reinterpret_cast<std::uintptr_t>(result.focus))
        +",\"input_count\":"+std::to_string(result.inputCount)+",\"error\":"+std::to_string(result.error)
        +",\"sent\":"+(result.sent?"true":"false")+'}');
}
static bool navigation(IUIAutomation* automation,const std::filesystem::path& output,WORD key)
{
    if (!exactMainReady() || ++scoreNavigationAttempts>48 || Clock::now()>=deadline) return false;
    auto result=SendOwnedKey(targetPid,targetProcess,mainWindow(),key);++keyboardGestureAttempts;
    recordInput(key==VK_F6?"F6_focus_navigation":"Tab_focus_navigation",result);
    if (!result.sent) { keyboardFailure=true;return false; }
    Sleep(120);return true;
}
static bool acquireScoreFocus(IUIAutomation* automation,const std::filesystem::path& output)
{
    if (liveScoreFocus(automation)) return true;
    // Source F6 selects a section; Tab selects panels. Observe after every one.
    for (int section=0;section<7;++section) {
        if (!navigation(automation,output,VK_F6)) return false;
        if (liveScoreFocus(automation)) return true;
        for (int panel=0;panel<5;++panel) {
            if (!navigation(automation,output,VK_TAB)) return false;
            if (liveScoreFocus(automation)) return true;
        }
    }
    return false;
}
static bool gesture(IUIAutomation* automation,ScoreKey key,const char* label)
{
    if (!liveScoreFocus(automation) || ++keyboardGestureAttempts>60) return false;
    auto result=SendOwnedScoreKey(targetPid,targetProcess,mainWindow(),key);recordInput(label,result);
    if (!result.sent) {keyboardFailure=true;return false;}
    Sleep(150);
    return liveScoreFocus(automation);
}
int wmain(int argc,wchar_t** argv)
{
    std::filesystem::path output;std::wstring phase;bool argsOkay=true;
    for (int i=1;i<argc;++i) {
        if (i+1>=argc) {argsOkay=false;break;}
        std::wstring option=argv[i],value=argv[++i];
        if (option==L"--pid") {
            wchar_t* end=nullptr;unsigned long parsed=wcstoul(value.c_str(),&end,10);
            if (!parsed || !end || *end) argsOkay=false;else targetPid=static_cast<DWORD>(parsed);
        } else if (option==L"--output") output=value;
        else if (option==L"--phase") phase=value;
        else argsOkay=false;
    }
    if (!argsOkay || !targetPid || output.empty() || !std::filesystem::is_directory(output)
        || (phase!=L"edit-save" && phase!=L"undo-save" && phase!=L"redo-save")) return 2;
    targetProcess=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,targetPid);
    if (!targetProcess) return 2;
    deadline=Clock::now()+std::chrono::seconds(60);
    const HRESULT initialized=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    ComPtr<IUIAutomation> automation;HRESULT created=FAILED(initialized)?initialized:CoCreateInstance(CLSID_CUIAutomation,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&automation));
    bool passed=false;std::string error;
    if (SUCCEEDED(created) && automation) {
        // Startup may still be loading the one native score. No input occurs yet.
        while (alive() && Clock::now()<deadline && !exactMainReady()) Sleep(100);
        diagnosticSnapshot(automation.Get(),output,L"tree-before");
        if (acquireScoreFocus(automation.Get(),output)) {
            if (phase==L"edit-save") {
                passed=gesture(automation.Get(),ScoreKey::first,"CtrlHome_first_element")
                    &&gesture(automation.Get(),ScoreKey::noteInput,"N_note_input")
                    &&gesture(automation.Get(),ScoreKey::quarter,"5_quarter")
                    &&gesture(automation.Get(),ScoreKey::c,"C")&&gesture(automation.Get(),ScoreKey::d,"D")
                    &&gesture(automation.Get(),ScoreKey::e,"E")&&gesture(automation.Get(),ScoreKey::f,"F")
                    &&gesture(automation.Get(),ScoreKey::escape,"Escape_exit_note_input");
            } else if (phase==L"undo-save") passed=gesture(automation.Get(),ScoreKey::undo,"CtrlZ_single_undo");
            else passed=gesture(automation.Get(),ScoreKey::redo,"CtrlY_single_redo");
            if (passed) passed=gesture(automation.Get(),ScoreKey::save,"CtrlS_save_existing_native_file");
        }
        diagnosticSnapshot(automation.Get(),output,L"tree-after");
        passed=passed&&!keyboardFailure&&alive()&&exactMainReady()&&liveScoreFocus(automation.Get());
        if (!passed) error="Exact local score focus ancestry or an ordinary-key phase was not proved; no later edit gesture was attempted.";
    } else error="Independent UI Automation client could not initialize.";
    std::ofstream report(output/L"score-edit-phase.json",std::ios::binary);
    report<<"{\"schema_version\":1,\"pid\":"<<targetPid<<",\"phase\":"<<jsonQuoted(phase)
        <<",\"status\":\""<<(passed?"passed_owned_score_keyboard_phase":"failed_or_blocked")
        <<"\",\"raw_tree_incomplete_observed\":"<<(diagnosticTreeIncomplete?"true":"false")
        <<",\"keyboard_failure\":"<<(keyboardFailure?"true":"false")<<",\"gestures\":"<<keyboardGestureAttempts
        <<",\"navigation_gestures\":"<<scoreNavigationAttempts<<",\"error\":"<<jsonQuoted(std::wstring(error.begin(),error.end()))<<",\"actions\":[";
    for(size_t i=0;i<actions.size();++i){if(i)report<<',';report<<actions[i];}report<<"],\"local_focus_scope\":\"focused-element-and-ancestors-only\",\"local_score_focus_verified\":"<<(passed?"true":"false")<<",\"score_focus_evidence\":[";
    for(size_t i=0;i<focusEvidence.size();++i){if(i)report<<',';report<<focusEvidence[i];}report<<"]}";report.close();
    automation.Reset();if(SUCCEEDED(initialized))CoUninitialize();CloseHandle(targetProcess);return passed?0:2;
}
