// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
// Read-only native readiness evidence; no activation, invocation or input.
#define NOMINMAX
#include <windows.h>
#include <UIAutomation.h>
#include <wrl/client.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
using Clock = std::chrono::steady_clock;
static DWORD targetPid = 0;
static HANDLE targetProcess = nullptr;
static Clock::time_point deadline;
static bool alive()
{
    DWORD code = 0;
    return targetProcess && targetProcess != INVALID_HANDLE_VALUE && GetProcessId(targetProcess) == targetPid
           && GetExitCodeProcess(targetProcess, &code) && code == STILL_ACTIVE
           && WaitForSingleObject(targetProcess, 0) == WAIT_TIMEOUT;
}
static bool budget() { return Clock::now() < deadline && alive(); }
static bool owned(HWND window)
{
    DWORD pid = 0;
    return window && GetWindowThreadProcessId(window, &pid) && pid == targetPid;
}
static std::wstring title(HWND window)
{
    wchar_t value[513] {};
    GetWindowTextW(window, value, 513);
    return value;
}
static std::vector<HWND> windows()
{
    std::vector<HWND> found;
    EnumWindows([](HWND window, LPARAM parameter) -> BOOL {
        auto& list = *reinterpret_cast<std::vector<HWND>*>(parameter);
        if (!budget() || list.size() >= 64) return FALSE;
        if (owned(window) && IsWindowVisible(window)) list.push_back(window);
        return TRUE;
    }, reinterpret_cast<LPARAM>(&found));
    return found;
}
static bool introduction(HWND window)
{
    const std::wstring name = title(window);
    if (!owned(window) || !IsWindowVisible(window) || !IsWindowEnabled(window)
        || (name != L"Introduction" && name != L"Introduction - Cadence Studio"
            && name != L"Getting started" && name != L"Getting started - Cadence Studio")) return false;
    HWND owner = GetWindow(window, GW_OWNER);
    for (unsigned hops = 1; owner && hops <= 8; ++hops) {
        if (!owned(owner)) return false;
        HWND next = GetWindow(owner, GW_OWNER);
        if (!next) return IsWindowVisible(owner) && !IsWindowEnabled(owner);
        owner = next;
    }
    return false;
}
static std::string quoted(const std::wstring& value)
{
    const int size = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string encoded(size > 0 ? size : 0, '\0'), result = "\"";
    if (size > 0) WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), encoded.data(), size, nullptr, nullptr);
    for (unsigned char c : encoded) {
        if (c == '\\' || c == '"') { result += '\\'; result += static_cast<char>(c); }
        else if (c == '\n') result += "\\n";
        else if (c == '\r') result += "\\r";
        else if (c == '\t') result += "\\t";
        else result += c < 32 ? '?' : static_cast<char>(c);
    }
    return result + '"';
}
struct Node {
    std::wstring name;
    int pid = 0, type = 0, depth = 0;
    BOOL enabled = FALSE, offscreen = TRUE;
    HRESULT nameHr = E_PENDING, pidHr = E_PENDING, typeHr = E_PENDING, enabledHr = E_PENDING, offscreenHr = E_PENDING;
};
static bool semantic(const Node& node)
{
    const bool type = node.type == UIA_RadioButtonControlTypeId || node.type == UIA_TabItemControlTypeId || node.type == UIA_ButtonControlTypeId;
    const std::vector<std::wstring> names { L"Accueil", L"Home", L"Partition", L"Partitions", L"Score", L"Scores", L"Publier", L"Publish" };
    return SUCCEEDED(node.nameHr) && SUCCEEDED(node.pidHr) && SUCCEEDED(node.typeHr) && SUCCEEDED(node.enabledHr) && SUCCEEDED(node.offscreenHr)
           && node.pid == static_cast<int>(targetPid) && type && node.enabled && !node.offscreen
           && std::find(names.begin(), names.end(), node.name) != names.end();
}
static void walk(IUIAutomationTreeWalker* walker, IUIAutomationElement* element, int depth,
                 std::vector<Node>& nodes, bool& ready, HRESULT& traversalHr)
{
    if (!element || ready || nodes.size() >= 400 || depth > 12 || !budget()) return;
    Node node;
    node.depth = depth;
    BSTR name = nullptr;
    node.nameHr = budget() ? element->get_CurrentName(&name) : E_ABORT;
    if (name) node.name.assign(name, std::min<UINT>(SysStringLen(name), 512));
    SysFreeString(name);
    node.pidHr = budget() ? element->get_CurrentProcessId(&node.pid) : E_ABORT;
    node.typeHr = budget() ? element->get_CurrentControlType(&node.type) : E_ABORT;
    node.enabledHr = budget() ? element->get_CurrentIsEnabled(&node.enabled) : E_ABORT;
    node.offscreenHr = budget() ? element->get_CurrentIsOffscreen(&node.offscreen) : E_ABORT;
    nodes.push_back(node);
    ready = semantic(node);
    if (ready || depth >= 12 || !budget() || FAILED(node.pidHr) || (node.pid != 0 && node.pid != static_cast<int>(targetPid))) return;
    ComPtr<IUIAutomationElement> child;
    traversalHr = walker->GetFirstChildElement(element, &child);
    if (FAILED(traversalHr)) return;
    while (child && !ready && nodes.size() < 400 && budget()) {
        walk(walker, child.Get(), depth + 1, nodes, ready, traversalHr);
        if (ready || !budget()) break;
        ComPtr<IUIAutomationElement> sibling;
        traversalHr = walker->GetNextSiblingElement(child.Get(), &sibling);
        if (FAILED(traversalHr)) break;
        child = sibling;
    }
}
struct Window { HWND handle = nullptr, owner = nullptr; std::wstring name; bool enabled = false; HRESULT elementHr = E_PENDING; };

int wmain(int argc, wchar_t** argv)
{
    std::filesystem::path output;
    if (argc != 5) return 2;
    for (int i = 1; i < argc; i += 2) {
        const std::wstring arg(argv[i]), value(argv[i + 1]);
        if (arg == L"--pid" && !targetPid && !value.empty() && value.size() <= 10) {
            unsigned long long pid = 0;
            for (wchar_t c : value) { if (c < L'0' || c > L'9') return 2; pid = pid * 10 + (c - L'0'); }
            if (!pid || pid > MAXDWORD) return 2;
            targetPid = static_cast<DWORD>(pid);
        } else if (arg == L"--output" && output.empty()) output = value;
        else return 2;
    }
    std::error_code error;
    if (!targetPid || output.empty() || !std::filesystem::is_directory(output, error) || error
        || std::filesystem::exists(output / L"native-readiness.json", error) || error) return 2;
    deadline = Clock::now() + std::chrono::seconds(35);
    targetProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, targetPid);
    const DWORD processError = targetProcess ? ERROR_SUCCESS : GetLastError();
    const HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    HRESULT activated = E_PENDING, queryHr = E_PENDING, connectionHr = E_PENDING, transactionHr = E_PENDING, walkerHr = E_PENDING, traversalHr = E_PENDING;
    ComPtr<IUIAutomation> automation;
    ComPtr<IUIAutomation2> bounded;
    ComPtr<IUIAutomationTreeWalker> walker;
    if (SUCCEEDED(initialized) && budget()) {
        activated = CoCreateInstance(__uuidof(CUIAutomation8), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        if (FAILED(activated) && budget()) activated = CoCreateInstance(__uuidof(CUIAutomation), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        if (SUCCEEDED(activated) && automation && budget()) queryHr = automation.As(&bounded);
        if (SUCCEEDED(queryHr) && bounded && budget()) connectionHr = bounded->put_ConnectionTimeout(800);
        if (SUCCEEDED(connectionHr) && budget()) transactionHr = bounded->put_TransactionTimeout(1000);
        if (SUCCEEDED(transactionHr) && budget()) walkerHr = automation->get_RawViewWalker(&walker);
    }
    bool ready = false, semanticReady = false, introductionReady = false;
    int polls = 0;
    std::vector<Node> nodes;
    std::vector<Window> observed;
    while (budget()) {
        ++polls; nodes.clear(); observed.clear(); semanticReady = false; introductionReady = false;
        for (HWND window : windows()) {
            if (!budget()) break;
            Window record { window, GetWindow(window, GW_OWNER), title(window), IsWindowEnabled(window) != FALSE };
            introductionReady = introductionReady || introduction(window);
            if (walker && budget()) {
                ComPtr<IUIAutomationElement> element;
                record.elementHr = automation->ElementFromHandle(window, &element);
                if (SUCCEEDED(record.elementHr)) walk(walker.Get(), element.Get(), 0, nodes, semanticReady, traversalHr);
            }
            observed.push_back(record);
        }
        ready = alive() && (semanticReady || introductionReady);
        if (ready) break;
        const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
        if (remaining > 0 && alive()) Sleep(static_cast<DWORD>(remaining < 100 ? remaining : 100));
    }
    if (!alive()) ready = false;
    const char* status = ready ? (semanticReady ? "ready_owned_semantic_control" : "ready_owned_introduction_dialog")
                              : (!alive() ? "blocked_process_not_alive" : "blocked_semantic_readiness_deadline");
    std::ofstream report(output / L"native-readiness.json", std::ios::binary);
    report << "{\"schema_version\":1,\"scope\":\"Read-only owned UI readiness; no UI action or functional validation\",\"ready\":" << (ready ? "true" : "false")
           << ",\"status\":\"" << status << "\",\"pid\":" << targetPid << ",\"poll_count\":" << polls << ",\"max_seconds\":35,\"max_nodes\":400,\"max_depth\":12"
           << ",\"node_limit_reached\":" << (nodes.size() >= 400 ? "true" : "false") << ",\"ui_actions_performed\":false"
           << ",\"process_open_error\":" << processError << ",\"process_alive\":" << (alive() ? "true" : "false")
           << ",\"com_initialization_hresult\":" << static_cast<long>(initialized) << ",\"com_activation_hresult\":" << static_cast<long>(activated)
           << ",\"uia2_query_hresult\":" << static_cast<long>(queryHr) << ",\"connection_timeout_hresult\":" << static_cast<long>(connectionHr)
           << ",\"transaction_timeout_hresult\":" << static_cast<long>(transactionHr) << ",\"walker_hresult\":" << static_cast<long>(walkerHr)
           << ",\"last_traversal_hresult\":" << static_cast<long>(traversalHr) << ",\"windows\":[";
    for (size_t i = 0; i < observed.size(); ++i) {
        const Window& w = observed[i]; if (i) report << ',';
        report << "{\"handle\":" << reinterpret_cast<std::uintptr_t>(w.handle) << ",\"owner\":" << reinterpret_cast<std::uintptr_t>(w.owner)
               << ",\"title\":" << quoted(w.name) << ",\"enabled\":" << (w.enabled ? "true" : "false") << ",\"element_from_handle_hresult\":" << static_cast<long>(w.elementHr) << '}';
    }
    report << "],\"nodes\":[";
    for (size_t i = 0; i < nodes.size(); ++i) {
        const Node& n = nodes[i]; if (i) report << ',';
        report << "{\"name\":" << quoted(n.name) << ",\"type\":" << n.type << ",\"pid\":" << n.pid << ",\"depth\":" << n.depth
               << ",\"enabled\":" << (n.enabled ? "true" : "false") << ",\"offscreen\":" << (n.offscreen ? "true" : "false")
               << ",\"name_hresult\":" << static_cast<long>(n.nameHr) << ",\"pid_hresult\":" << static_cast<long>(n.pidHr)
               << ",\"type_hresult\":" << static_cast<long>(n.typeHr) << ",\"enabled_hresult\":" << static_cast<long>(n.enabledHr)
               << ",\"offscreen_hresult\":" << static_cast<long>(n.offscreenHr) << '}';
    }
    report << "]}"; report.close();
    walker.Reset(); bounded.Reset(); automation.Reset();
    if (SUCCEEDED(initialized)) CoUninitialize();
    const bool written = !report.fail();
    if (targetProcess) CloseHandle(targetProcess);
    return ready && written ? 0 : 2;
}
