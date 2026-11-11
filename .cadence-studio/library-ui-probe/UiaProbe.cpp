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

using Microsoft::WRL::ComPtr;
using Clock = std::chrono::steady_clock;
static DWORD targetPid = 0;
static HANDLE targetProcess = nullptr;
static Clock::time_point deadline;
static std::vector<std::string> actions;

static std::string utf8(const std::wstring& value)
{
    if (value.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string out(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), out.data(), n, nullptr, nullptr);
    return out;
}
static std::string quoted(const std::wstring& value)
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
        actions.push_back("{\"action\":\"close_owned_introduction_only\",\"title\":" + quoted(title)
                          + ",\"pid\":" + std::to_string(targetPid) + ",\"posted\":" + (ok ? "true" : "false") + "}");
        posted = posted || ok;
    }
    return posted;
}

struct Node {
    ComPtr<IUIAutomationElement> element;
    std::wstring name, id;
    int pid = 0, type = 0, depth = 0;
    BOOL enabled = FALSE, offscreen = TRUE;
};
static void walk(IUIAutomationTreeWalker* walker, IUIAutomationElement* element, int depth, std::vector<Node>& nodes)
{
    if (!element || nodes.size() >= 1200 || depth > 18 || Clock::now() > deadline || !alive()) return;
    Node node;
    node.element = element; node.depth = depth;
    BSTR name = nullptr, id = nullptr;
    element->get_CurrentName(&name); node.name = text(name);
    element->get_CurrentAutomationId(&id); node.id = text(id);
    element->get_CurrentProcessId(&node.pid); element->get_CurrentControlType(&node.type);
    element->get_CurrentIsEnabled(&node.enabled); element->get_CurrentIsOffscreen(&node.offscreen);
    nodes.push_back(node);
    if (node.pid != static_cast<int>(targetPid) && node.pid != 0) return;
    ComPtr<IUIAutomationElement> child;
    if (FAILED(walker->GetFirstChildElement(element, &child))) return;
    while (child && nodes.size() < 1200 && Clock::now() <= deadline) {
        walk(walker, child.Get(), depth + 1, nodes);
        ComPtr<IUIAutomationElement> sibling;
        if (FAILED(walker->GetNextSiblingElement(child.Get(), &sibling))) break;
        child = sibling;
    }
}
static std::vector<Node> snapshot(IUIAutomation* automation, const std::filesystem::path& output, const wchar_t* phase)
{
    std::vector<Node> nodes;
    std::vector<std::string> inspectedWindows;
    ComPtr<IUIAutomationTreeWalker> walker;
    const HRESULT walkerResult = automation->get_RawViewWalker(&walker);
    if (SUCCEEDED(walkerResult)) {
        for (HWND window : windows()) {
            ComPtr<IUIAutomationElement> element;
            if (!owned(window)) continue;
            const HRESULT elementResult = automation->ElementFromHandle(window, &element);
            inspectedWindows.push_back("{\"handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(window))
                                       + ",\"title\":" + quoted(windowTitle(window))
                                       + ",\"pid\":" + std::to_string(targetPid)
                                       + ",\"enabled\":" + (IsWindowEnabled(window) ? "true" : "false")
                                       + ",\"owner_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(GetWindow(window, GW_OWNER)))
                                       + ",\"element_from_handle_hresult\":" + std::to_string(static_cast<long>(elementResult)) + '}');
            if (SUCCEEDED(elementResult)) walk(walker.Get(), element.Get(), 0, nodes);
        }
    }
    std::ofstream file(output / (std::wstring(phase) + L".json"), std::ios::binary);
    file << "{\"pid\":" << targetPid << ",\"bounded\":true,\"max_nodes\":1200,\"max_depth\":18,\"deadline_reached\":"
         << (Clock::now() > deadline ? "true" : "false") << ",\"node_limit_reached\":" << (nodes.size() >= 1200 ? "true" : "false") << ",\"nodes\":[";
    bool first = true;
    for (const Node& node : nodes) {
        if (!first) file << ',';
        first = false;
        file << "{\"name\":" << quoted(node.name) << ",\"automation_id\":" << quoted(node.id)
             << ",\"control_type\":" << node.type << ",\"pid\":" << node.pid << ",\"depth\":" << node.depth
             << ",\"enabled\":" << (node.enabled ? "true" : "false") << ",\"offscreen\":" << (node.offscreen ? "true" : "false") << '}';
    }
    file << "],\"walker_hresult\":" << static_cast<long>(walkerResult) << ",\"inspected_windows\":[";
    for (size_t i = 0; i < inspectedWindows.size(); ++i) { if (i) file << ','; file << inspectedWindows[i]; }
    file << "]}";
    return nodes;
}
static bool interactiveType(int type)
{
    return type == UIA_ButtonControlTypeId || type == UIA_TabItemControlTypeId || type == UIA_RadioButtonControlTypeId
           || type == UIA_ListItemControlTypeId || type == UIA_TreeItemControlTypeId;
}
static const Node* find(const std::vector<Node>& nodes, const std::vector<std::wstring>& names)
{
    const Node* result = nullptr;
    for (const Node& node : nodes) {
        if (node.pid != static_cast<int>(targetPid) || !node.enabled || node.offscreen || !interactiveType(node.type)) continue;
        if (std::find(names.begin(), names.end(), node.name) == names.end()) continue;
        if (result) return nullptr; // No arbitrary choice between ambiguous controls.
        result = &node;
    }
    return result;
}
static bool invokeSemantic(const Node* node, const char* purpose)
{
    if (!node || !alive() || Clock::now() > deadline) return false;
    HWND main = mainWindow(); int pid = 0; BOOL enabled = FALSE, offscreen = TRUE;
    if (!owned(main) || !IsWindowEnabled(main) || FAILED(node->element->get_CurrentProcessId(&pid))
        || pid != static_cast<int>(targetPid) || FAILED(node->element->get_CurrentIsEnabled(&enabled)) || !enabled
        || FAILED(node->element->get_CurrentIsOffscreen(&offscreen)) || offscreen) return false;
    HRESULT result = E_NOINTERFACE;
    auto ownershipRechecked = [&]() {
        int currentPid = 0;
        HWND currentMain = mainWindow();
        return alive() && owned(currentMain) && IsWindowEnabled(currentMain)
               && SUCCEEDED(node->element->get_CurrentProcessId(&currentPid)) && currentPid == static_cast<int>(targetPid);
    };
    const char* pattern = "none";
    ComPtr<IUIAutomationSelectionItemPattern> selection;
    ComPtr<IUIAutomationInvokePattern> invoke;
    ComPtr<IUIAutomationLegacyIAccessiblePattern> legacy;
    if (SUCCEEDED(node->element->GetCurrentPatternAs(UIA_SelectionItemPatternId, IID_PPV_ARGS(&selection)))) {
        BOOL selected = FALSE;
        selection->get_CurrentIsSelected(&selected);
        result = selected ? S_OK : (ownershipRechecked() ? selection->Select() : E_ACCESSDENIED); pattern = selected ? "SelectionItem_already_selected" : "SelectionItem_Select";
    } else if (SUCCEEDED(node->element->GetCurrentPatternAs(UIA_InvokePatternId, IID_PPV_ARGS(&invoke)))) {
        result = ownershipRechecked() ? invoke->Invoke() : E_ACCESSDENIED; pattern = "Invoke";
    } else if (SUCCEEDED(node->element->GetCurrentPatternAs(UIA_LegacyIAccessiblePatternId, IID_PPV_ARGS(&legacy)))) {
        result = ownershipRechecked() ? legacy->DoDefaultAction() : E_ACCESSDENIED; pattern = "LegacyIAccessible_default_action";
    }
    actions.push_back(std::string("{\"action\":\"") + purpose + "\",\"name\":" + quoted(node->name)
                      + ",\"pid\":" + std::to_string(pid) + ",\"pattern\":\"" + pattern
                      + "\",\"hresult\":" + std::to_string(static_cast<long>(result)) + '}');
    return SUCCEEDED(result);
}

int wmain(int argc, wchar_t** argv)
{
    std::filesystem::path output;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (std::wstring(argv[i]) == L"--pid") targetPid = wcstoul(argv[i + 1], nullptr, 10);
        else if (std::wstring(argv[i]) == L"--output") output = argv[i + 1];
        else return 1;
    }
    if (!targetPid || output.empty() || !std::filesystem::is_directory(output)) return 1;
    targetProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, targetPid);
    if (!alive()) return 1;
    deadline = Clock::now() + std::chrono::seconds(55);
    std::string status = "blocked_uia_unavailable";
    bool contentObserved = false;
    bool navigationReady = false;
    int readinessPolls = 0;
    HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    HRESULT activated = initialized;
    if (SUCCEEDED(initialized)) {
        ComPtr<IUIAutomation> automation;
        activated = CoCreateInstance(__uuidof(CUIAutomation8), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        if (FAILED(activated)) activated = CoCreateInstance(__uuidof(CUIAutomation), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        ComPtr<IUIAutomation2> bounded;
        if (SUCCEEDED(activated) && SUCCEEDED(automation.As(&bounded))
            && SUCCEEDED(bounded->put_ConnectionTimeout(800)) && SUCCEEDED(bounded->put_TransactionTimeout(1000))) {
            const std::vector<std::wstring> homeNames { L"Accueil", L"Home" };
            const std::vector<std::wstring> scoreNames { L"Partitions", L"Scores" };
            const std::vector<std::wstring> libraryNames { L"Biblioth\u00e8que locale", L"Local library" };
            auto nodes = snapshot(automation.Get(), output, L"tree-before");
            // The first visible HWND may be the splash screen. Wait for real
            // semantic navigation controls within the same global deadline;
            // an empty provider tree is evidence of unreadiness, not success.
            while (Clock::now() < deadline && alive()) {
                ++readinessPolls;
                if (closeIntroductionOnly()) Sleep(400);
                nodes = snapshot(automation.Get(), output, L"tree-ready");
                navigationReady = find(nodes, homeNames) || find(nodes, scoreNames) || find(nodes, libraryNames);
                if (navigationReady) break;
                Sleep(400);
            }
            nodes = snapshot(automation.Get(), output, L"tree-after-introduction");
            if (navigationReady && invokeSemantic(find(nodes, homeNames), "activate_home")) {
                Sleep(500); nodes = snapshot(automation.Get(), output, L"tree-after-home");
            }
            bool activatedLibrary = false;
            bool activatedScores = false;
            while (navigationReady && alive() && Clock::now() < deadline) {
                if (closeIntroductionOnly()) Sleep(400);
                nodes = snapshot(automation.Get(), output, L"tree-navigation-ready");
                if (const Node* library = find(nodes, libraryNames)) {
                    activatedLibrary = invokeSemantic(library, "activate_local_library");
                    if (activatedLibrary) break;
                } else if (!activatedScores && invokeSemantic(find(nodes, scoreNames), "activate_scores")) {
                    activatedScores = true;
                    nodes = snapshot(automation.Get(), output, L"tree-after-scores");
                }
                Sleep(400);
            }
            if (activatedLibrary) Sleep(750);
            for (int attempt = 0; attempt < 8 && Clock::now() < deadline; ++attempt) {
                nodes = snapshot(automation.Get(), output, L"tree-final");
                const Node* add = find(nodes, { L"Ajouter des partitions\u2026", L"Ajouter des partitions...", L"Add scores\u2026" });
                contentObserved = activatedLibrary && add != nullptr;
                if (contentObserved || !activatedLibrary) break;
                Sleep(400);
            }
            status = contentObserved ? "library_tab_active_and_add_control_observed" : "blocked_library_controls_or_semantic_action_unavailable";
            if (!contentObserved && owned(mainWindow()) && !IsWindowEnabled(mainWindow())) status = "blocked_owned_modal_remaining_after_introduction";
            if (!contentObserved && Clock::now() > deadline) status = navigationReady ? "blocked_uia_inspection_deadline" : "blocked_semantic_navigation_not_ready_before_deadline";
        }
        automation.Reset(); bounded.Reset(); CoUninitialize();
    }
    std::ofstream result(output / L"uia-report.json", std::ios::binary);
    result << "{\"scope\":\"Owned PID accessibility inspection and semantic navigation only; no score opened or changed\",\"pid\":"
           << targetPid << ",\"status\":\"" << status << "\",\"com_activation_hresult\":" << static_cast<long>(activated)
           << ",\"library_content_observed\":" << (contentObserved ? "true" : "false")
           << ",\"semantic_navigation_ready\":" << (navigationReady ? "true" : "false")
           << ",\"readiness_polls\":" << readinessPolls << ",\"global_deadline_seconds\":55,\"actions\":[";
    for (size_t i = 0; i < actions.size(); ++i) { if (i) result << ','; result << actions[i]; }
    result << "],\"windows\":[";
    bool firstWindow = true;
    for (HWND window : windows()) {
        if (!firstWindow) result << ',';
        firstWindow = false;
        result << "{\"handle\":" << reinterpret_cast<std::uintptr_t>(window) << ",\"title\":" << quoted(windowTitle(window))
               << ",\"owner_handle\":" << reinterpret_cast<std::uintptr_t>(GetWindow(window, GW_OWNER))
               << ",\"pid\":" << targetPid << ",\"enabled\":" << (IsWindowEnabled(window) ? "true" : "false") << '}';
    }
    result << "],\"score_editing_tested\":false,\"favorites_tested\":false,\"listening_tested\":false}";
    CloseHandle(targetProcess);
    return contentObserved ? 0 : 2;
}
