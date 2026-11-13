// SPDX-License-Identifier: GPL-3.0-only
// Observe only the PID supplied by our launcher; one bounded owned F10 mixer observation.
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <UIAutomation.h>
#include <wrl/client.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cwchar>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <stdexcept>
#include <vector>
#include "OwnedKeyboard.h"
#include "ObservationGraph.h"
using cadence_observation::RuntimeId;

using Microsoft::WRL::ComPtr;
using Clock = std::chrono::steady_clock;
static DWORD targetPid = 0;
static HANDLE targetProcess = nullptr;
static Clock::time_point deadline;
static std::vector<std::string> actions;
static std::vector<std::string> keyboardFrames;
static int keyboardGestureAttempts = 0;
static int f10GestureAttempts = 0, tabGestureAttempts = 0, rightGestureAttempts = 0, leftGestureAttempts = 0, downGestureAttempts = 0, returnGestureAttempts = 0;
static bool keyboardFailure = false;
static bool observationTreeIncomplete = false;
static bool foreignNodeObserved = false;
static bool runtimeIdentityUnknown = false;
static long runtimeIdentityFailureHresult = S_OK;
static size_t totalCycleEdges = 0, totalDuplicateEdges = 0;
static int endGestureAttempts = 0;

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
    return targetProcess && GetProcessId(targetProcess) == targetPid
        && WaitForSingleObject(targetProcess, 0) == WAIT_TIMEOUT
        && GetExitCodeProcess(targetProcess, &exitCode) && exitCode == STILL_ACTIVE;
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

struct Node {
    ComPtr<IUIAutomationElement> element;
    std::wstring name, id;
    RuntimeId runtimeId;
    int pid = 0, type = 0, depth = 0;
    BOOL enabled = FALSE, offscreen = TRUE, focused = FALSE;
};
static std::wstring controlLabel(const std::wstring& name)
{
    // MuseScore's accessible Name prepends the current panel to its focused
    // control (AccessibleItemInterface::text). Strip only known source labels.
    const std::vector<std::wstring> prefixes {
        L"Panneau Notes priv\u00e9es de pratique, ", L"Panneau Partitions, ", L"Scores panel, ",
        L"Panneau Barre d'onglets des partitions, ", L"Scores tab bar panel, ",
        L"Panneau Biblioth\u00e8que locale, ", L"Biblioth\u00e8que locale panel, ", L"Local library panel, ", L"Panneau Dropdown, ", L"Dropdown panel, "
    };
    for (const auto& prefix : prefixes) if (name.rfind(prefix, 0) == 0) return name.substr(prefix.size());
    return name;
}
static RuntimeId runtimeIdentity(IUIAutomationElement* element)
{
    int pid = 0;
    if (!element || FAILED(element->get_CurrentProcessId(&pid)) || pid != static_cast<int>(targetPid)) {
        foreignNodeObserved = true; return {};
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
        runtimeIdentityUnknown = true; runtimeIdentityFailureHresult = FAILED(fetched) ? static_cast<long>(fetched) : E_INVALIDARG; observationTreeIncomplete = true; return {};
    }
    RuntimeId id;
    for (LONG index = first; index <= last; ++index) {
        int part = 0;
        const HRESULT readPart = SafeArrayGetElement(raw,&index,&part);
        if (FAILED(readPart)) {
            runtimeIdentityUnknown = true; runtimeIdentityFailureHresult = static_cast<long>(readPart); observationTreeIncomplete = true; return {};
        }
        id.push_back(part);
        if (index == last) break; // Avoid LONG overflow for an invalid upper bound.
    }
    if (id.empty()) { runtimeIdentityUnknown = true; runtimeIdentityFailureHresult = E_UNEXPECTED; observationTreeIncomplete = true; }
    return id;
}
static std::string runtimeJson(const RuntimeId& id)
{
    std::string out = "[";
    for (size_t i = 0; i < id.size(); ++i) { if (i) out += ','; out += std::to_string(id[i]); }
    return out + ']';
}
static Node focusedNode(IUIAutomation* automation)
{
    Node node;
    if (SUCCEEDED(automation->GetFocusedElement(&node.element)) && node.element) {
        if (FAILED(node.element->get_CurrentProcessId(&node.pid)) || node.pid != static_cast<int>(targetPid)) return node;
        BSTR name = nullptr;
        const HRESULT named = node.element->get_CurrentName(&name); node.name = text(name);
        const HRESULT typed = node.element->get_CurrentControlType(&node.type);
        const HRESULT enabled = node.element->get_CurrentIsEnabled(&node.enabled);
        const HRESULT offscreen = node.element->get_CurrentIsOffscreen(&node.offscreen);
        const HRESULT focused = node.element->get_CurrentHasKeyboardFocus(&node.focused);
        node.runtimeId = runtimeIdentity(node.element.Get());
        if (FAILED(named) || FAILED(typed) || FAILED(enabled) || FAILED(offscreen) || FAILED(focused) || node.runtimeId.empty()) node.focused = FALSE;
    }
    return node;
}
static void walk(IUIAutomationTreeWalker* walker, IUIAutomationElement* element, const RuntimeId& id,
                 int depth, std::vector<Node>& nodes, cadence_observation::Graph& graph,
                 const RuntimeId& parent, const std::string& relation)
{
    if (!element) return;
    if (Clock::now() > deadline || !alive()) { observationTreeIncomplete = true; return; }
    const auto visit = graph.enter(id,parent,relation);
    if (visit == cadence_observation::Visit::cycle || visit == cadence_observation::Visit::duplicate) return;
    if (visit != cadence_observation::Visit::first || depth > 18) { observationTreeIncomplete = true; return; }
    cadence_observation::ActiveScope leave(graph,id);
    Node node;
    node.element = element; node.runtimeId = id; node.depth = depth;
    if (FAILED(element->get_CurrentProcessId(&node.pid)) || node.pid != static_cast<int>(targetPid)) {
        foreignNodeObserved = true; return;
    }
    BSTR name = nullptr, automationId = nullptr;
    const HRESULT named = element->get_CurrentName(&name); node.name = text(name);
    const HRESULT identified = element->get_CurrentAutomationId(&automationId); node.id = text(automationId);
    const HRESULT typed = element->get_CurrentControlType(&node.type);
    const HRESULT enabled = element->get_CurrentIsEnabled(&node.enabled);
    const HRESULT offscreen = element->get_CurrentIsOffscreen(&node.offscreen);
    const HRESULT focused = element->get_CurrentHasKeyboardFocus(&node.focused);
    if (FAILED(named) || FAILED(identified) || FAILED(typed) || FAILED(enabled) || FAILED(offscreen) || FAILED(focused)) {
        observationTreeIncomplete = true; return;
    }
    nodes.push_back(node);
    ComPtr<IUIAutomationElement> child;
    if (FAILED(walker->GetFirstChildElement(element,&child))) { observationTreeIncomplete = true; return; }
    std::set<RuntimeId> siblings;
    std::string edge = "first_child";
    RuntimeId edgeSource = id;
    while (child && Clock::now() <= deadline && alive()) {
        const auto childId = runtimeIdentity(child.Get());
        if (childId.empty()) { observationTreeIncomplete = true; break; }
        if (!siblings.insert(childId).second) {
            if (!graph.siblingRepeat(edgeSource,childId)) observationTreeIncomplete = true;
            break; // A finite, recorded provider sibling cycle; never loop it.
        }
        walk(walker,child.Get(),childId,depth+1,nodes,graph,edgeSource,edge);
        if (runtimeIdentityUnknown || foreignNodeObserved || observationTreeIncomplete) break;
        ComPtr<IUIAutomationElement> sibling;
        if (FAILED(walker->GetNextSiblingElement(child.Get(),&sibling))) { observationTreeIncomplete = true; break; }
        edgeSource = childId; child = sibling; edge = "next_sibling";
    }
    if (Clock::now() > deadline || !alive()) observationTreeIncomplete = true;
}
static std::vector<Node> snapshot(IUIAutomation* automation, const std::filesystem::path& output, const wchar_t* phase)
{
    std::vector<Node> nodes;
    cadence_observation::Graph graph;
    std::vector<std::string> inspectedWindows;
    ComPtr<IUIAutomationTreeWalker> walker;
    const HRESULT walkerResult = automation->get_RawViewWalker(&walker);
    if (FAILED(walkerResult)) observationTreeIncomplete = true;
    if (SUCCEEDED(walkerResult)) {
        for (HWND window : windows()) {
            ComPtr<IUIAutomationElement> element;
            if (!owned(window)) continue;
            const HRESULT elementResult = automation->ElementFromHandle(window, &element);
            if (FAILED(elementResult)) observationTreeIncomplete = true;
            inspectedWindows.push_back("{\"handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(window))
                                       + ",\"title\":" + jsonQuoted(windowTitle(window))
                                       + ",\"pid\":" + std::to_string(targetPid)
                                       + ",\"enabled\":" + (IsWindowEnabled(window) ? "true" : "false")
                                       + ",\"owner_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(GetWindow(window, GW_OWNER)))
                                       + ",\"element_from_handle_hresult\":" + std::to_string(static_cast<long>(elementResult)) + '}');
            if (SUCCEEDED(elementResult)) {
                const auto id = runtimeIdentity(element.Get());
                walk(walker.Get(),element.Get(),id,0,nodes,graph,{},"owned_window");
            }
        }
    }
    if (nodes.empty() || nodes.size() >= 1200 || Clock::now() > deadline) observationTreeIncomplete = true;
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
    file << "],\"runtime_identity_unknown\":" << (runtimeIdentityUnknown ? "true" : "false")
         << ",\"runtime_identity_failure_hresult\":" << runtimeIdentityFailureHresult
         << ",\"unique_runtime_ids\":" << graph.uniqueNodes() << ",\"cycle_edges\":" << graph.cycleEdges
         << ",\"duplicate_edges\":" << graph.duplicateEdges << ",\"graph_edges\":[";
    for (size_t i = 0; i < graph.edges.size(); ++i) {
        if (i) file << ',';
        const auto& edge = graph.edges[i];
        file << "{\"from\":" << runtimeJson(edge.from) << ",\"to\":" << runtimeJson(edge.to)
             << ",\"relation\":" << jsonQuoted(std::wstring(edge.relation.begin(),edge.relation.end()))
             << ",\"cycle\":" << (edge.cycle ? "true" : "false")
             << ",\"duplicate\":" << (edge.duplicate ? "true" : "false") << '}';
    }
    file << "]}";
    totalCycleEdges += graph.cycleEdges; totalDuplicateEdges += graph.duplicateEdges;
    return nodes;
}

// Only navigation observation is implemented below. No Invoke/ValuePattern,
// score shortcut, text input, Save, autosave injection or crash action exists.
struct ObservationHandle {
    HANDLE value = INVALID_HANDLE_VALUE;
    ~ObservationHandle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
};
struct ObservationHash {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    std::vector<UCHAR> object;
    ~ObservationHash() { if (hash) BCryptDestroyHash(hash); if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0); }
};
static constexpr const char* expectedExeSha = "dcfbf9155c6c972c37966a4b2b0dcd212133c8e31fb397c644dda800ac7122be";

static std::wstring fullLocalPath(const std::wstring& value)
{
    if (value.size() < 3 || value[1] != L':' || value[2] != L'\\'
        || !((value[0] >= L'A' && value[0] <= L'Z') || (value[0] >= L'a' && value[0] <= L'z'))
        || value.find_first_of(L"\r\n") != std::wstring::npos) throw std::runtime_error("absolute local path required");
    wchar_t buffer[32768] {};
    DWORD count = GetFullPathNameW(value.c_str(), 32768, buffer, nullptr);
    if (!count || count >= 32768) throw std::runtime_error("path could not be normalized");
    const std::filesystem::path path(buffer);
    for (auto current = path; !current.empty(); current = current.parent_path()) {
        const DWORD attr = GetFileAttributesW(current.c_str());
        if (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_REPARSE_POINT))
            throw std::runtime_error("reparse path refused");
        if (current == current.parent_path()) break;
    }
    return path.native();
}
static bool belowTemporary(const std::wstring& value)
{
    wchar_t buffer[32768] {};
    const DWORD count = GetEnvironmentVariableW(L"RUNNER_TEMP", buffer, 32768);
    if (!count || count >= 32768) return false;
    std::wstring prefix = fullLocalPath(buffer);
    while (!prefix.empty() && prefix.back() == L'\\') prefix.pop_back();
    prefix += L'\\';
    return value.size() > prefix.size() && _wcsnicmp(value.c_str(), prefix.c_str(), prefix.size()) == 0;
}
static std::string lockExecutableBytes(const std::wstring& path, ObservationHandle& file)
{
    file.value = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                             FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
    if (file.value == INVALID_HANDLE_VALUE) throw std::runtime_error("executable byte lock failed");
    ObservationHash state;
    if (BCryptOpenAlgorithmProvider(&state.algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0)
        throw std::runtime_error("SHA256 provider failed");
    DWORD objectBytes = 0, returned = 0;
    if (BCryptGetProperty(state.algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&objectBytes),
                          sizeof(objectBytes), &returned, 0) < 0 || returned != sizeof(objectBytes)
        || !objectBytes || objectBytes > 1024 * 1024) throw std::runtime_error("SHA256 object invalid");
    state.object.resize(objectBytes);
    if (BCryptCreateHash(state.algorithm, &state.hash, state.object.data(), objectBytes, nullptr, 0, 0) < 0)
        throw std::runtime_error("SHA256 hash creation failed");
    UCHAR bytes[65536] {}, result[32] {};
    DWORD got = 0;
    unsigned long long total = 0;
    for (;;) {
        if (!ReadFile(file.value, bytes, sizeof(bytes), &got, nullptr)) throw std::runtime_error("EXE read failed");
        if (!got) break;
        total += got;
        if (total > 256ULL * 1024 * 1024 || BCryptHashData(state.hash, bytes, got, 0) < 0)
            throw std::runtime_error("EXE size/hash refused");
    }
    if (BCryptFinishHash(state.hash, result, sizeof(result), 0) < 0) throw std::runtime_error("SHA256 finish failed");
    std::string out;
    const char* digits = "0123456789abcdef";
    for (const auto byte : result) { out += digits[byte >> 4]; out += digits[byte & 15]; }
    return out;
}
static bool imageMatches(const std::wstring& expected)
{
    wchar_t image[32768] {};
    DWORD count = 32768;
    return alive() && QueryFullProcessImageNameW(targetProcess, 0, image, &count)
        && _wcsicmp(expected.c_str(), image) == 0;
}
static std::string focusJson(const Node& node)
{
    return "{\"name\":" + jsonQuoted(node.name) + ",\"pid\":" + std::to_string(node.pid)
        + ",\"control_type\":" + std::to_string(node.type)
        + ",\"enabled\":" + (node.enabled ? "true" : "false")
        + ",\"offscreen\":" + (node.offscreen ? "true" : "false")
        + ",\"keyboard_focus\":" + (node.focused ? "true" : "false") + "}";
}
static bool safeObservationFocus(const Node& node)
{
    return !node.runtimeId.empty() && node.element && node.pid == static_cast<int>(targetPid) && node.focused && node.enabled && !node.offscreen
        && node.type != UIA_EditControlTypeId && node.type != UIA_TextControlTypeId
        && node.type != UIA_MenuControlTypeId && node.type != UIA_MenuBarControlTypeId
        && node.type != UIA_MenuItemControlTypeId && node.type != UIA_ComboBoxControlTypeId
        && node.type != UIA_SpinnerControlTypeId;
}

int wmain(int argc, wchar_t** argv)
{
    if (argc != 7 || std::wstring(argv[1]) != L"--pid" || std::wstring(argv[3]) != L"--exe"
        || std::wstring(argv[5]) != L"--output") return 2;
    std::filesystem::path output;
    std::string status = "blocked_observation_identity", error;
    std::vector<std::string> frames;
    bool comInitialized = false;
    bool outputCreatedByThisRun = false;
    ObservationHandle executable;
    int gestures = 0;
    try {
        size_t parsed = 0;
        unsigned long raw = std::stoul(argv[2], &parsed);
        if (!raw || parsed != std::wstring(argv[2]).size() || raw > MAXDWORD) throw std::runtime_error("invalid PID");
        targetPid = static_cast<DWORD>(raw);
        const std::wstring image = fullLocalPath(argv[4]);
        output = fullLocalPath(argv[6]);
        if (!belowTemporary(image) || !belowTemporary(output.native()) || std::filesystem::exists(output)
            || !std::filesystem::is_directory(output.parent_path())) throw std::runtime_error("new bounded runtime output required");
        outputCreatedByThisRun = std::filesystem::create_directory(output);
        if (!outputCreatedByThisRun) throw std::runtime_error("new output creation raced");
        if (lockExecutableBytes(image, executable) != expectedExeSha) throw std::runtime_error("actual2007 EXE bytes differ");
        targetProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, targetPid);
        if (!targetProcess || !imageMatches(image)) throw std::runtime_error("owned process image/handle mismatch");
        deadline = Clock::now() + std::chrono::seconds(75);
        const HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        if (FAILED(initialized)) throw std::runtime_error("COM initialization failed");
        comInitialized = true;
        ComPtr<IUIAutomation> automation;
        if (FAILED(CoCreateInstance(CLSID_CUIAutomation, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation)))
            || !automation) throw std::runtime_error("UIA creation failed");
        snapshot(automation.Get(), output, L"tree-initial");
        if (observationTreeIncomplete || foreignNodeObserved || Clock::now() >= deadline)
            throw std::runtime_error("initial UIA projection incomplete or outside owned PID");
        status = "mixer_observation_collected_no_parameter_qualification";
        for (int index = 0; index < 1 && Clock::now() < deadline; ++index) {
            const HWND main = mainWindow();
            const auto ownedWindows = windows();
            const Node before = focusedNode(automation.Get());
            frames.push_back("{\"phase\":\"before_f10\",\"index\":" + std::to_string(index)
                             + ",\"focus\":" + focusJson(before) + "}");
            // Unknown focus, text, menu or any modal blocks before insertion.
            if (!imageMatches(image) || ownedWindows.size() != 1 || ownedWindows[0] != main
                || !owned(main) || !IsWindowEnabled(main) || !safeObservationFocus(before)) {
                status = "blocked_before_f10_on_unproved_or_text_menu_modal_focus"; break;
            }
            const std::wstring beforeName = L"tree-before-f10-" + std::to_wstring(index);
            snapshot(automation.Get(), output, beforeName.c_str());
            if (observationTreeIncomplete || foreignNodeObserved || Clock::now() >= deadline) {
                status = "blocked_incomplete_owned_UIA_projection"; break;
            }
            const Node immediate = focusedNode(automation.Get());
            BOOL same = FALSE;
            if (!safeObservationFocus(immediate)
                || FAILED(automation->CompareElements(before.element.Get(), immediate.element.Get(), &same)) || !same) {
                status = "blocked_before_f10_focus_changed"; break;
            }
            const auto sent = SendOwnedKey(targetPid, targetProcess, main, VK_F10);
            ++gestures;
            actions.push_back("{\"action\":\"owned_f10_observation_only\",\"sent\":"
                + std::string(sent.sent ? "true" : "false") + ",\"error\":" + std::to_string(sent.error)
                + ",\"foreground_hwnd\":" + std::to_string(reinterpret_cast<std::uintptr_t>(sent.foreground))
                + ",\"focus_hwnd\":" + std::to_string(reinterpret_cast<std::uintptr_t>(sent.focus)) + "}");
            if (!sent.sent) { status = "blocked_owned_f10_input"; break; }
            Sleep(180);
            const std::wstring afterName = L"tree-after-f10-" + std::to_wstring(index);
            snapshot(automation.Get(), output, afterName.c_str());
            if (observationTreeIncomplete || foreignNodeObserved || Clock::now() >= deadline) {
                status = "blocked_incomplete_owned_UIA_projection"; break;
            }
            frames.push_back("{\"phase\":\"after_f10\",\"index\":" + std::to_string(index)
                             + ",\"focus\":" + focusJson(focusedNode(automation.Get())) + "}");
        }
        snapshot(automation.Get(), output, L"tree-final");
        if (observationTreeIncomplete || foreignNodeObserved || Clock::now() >= deadline)
            status = "blocked_incomplete_owned_UIA_projection";
    } catch (const std::exception& exception) { error = exception.what(); status = "blocked_observation_exception"; }
    if (outputCreatedByThisRun && !output.empty() && std::filesystem::is_directory(output)) {
        std::ofstream report(output / L"observation-report.json", std::ios::binary);
        report << "{\"schema_version\":1,\"status\":" << jsonQuoted(std::wstring(status.begin(), status.end()))
            << ",\"pid\":" << targetPid << ",\"expected_executable_sha256\":\"" << expectedExeSha
            << "\",\"score_edited\":false,\"recovery_tested\":false,\"backup_tested\":false,\"gestures_attempted\":" << gestures
            << ",\"gesture_limit\":1,\"tree_incomplete\":" << (observationTreeIncomplete ? "true" : "false")
            << ",\"runtime_identity_unknown\":" << (runtimeIdentityUnknown ? "true" : "false")
            << ",\"runtime_identity_failure_hresult\":" << runtimeIdentityFailureHresult
            << ",\"total_cycle_edges\":" << totalCycleEdges << ",\"total_duplicate_edges\":" << totalDuplicateEdges
            << ",\"foreign_node_refused\":" << (foreignNodeObserved ? "true" : "false")
            << ",\"error\":" << jsonQuoted(std::wstring(error.begin(), error.end())) << ",\"actions\":[";
        for (size_t i = 0; i < actions.size(); ++i) { if (i) report << ','; report << actions[i]; }
        report << "],\"focused_frames\":[";
        for (size_t i = 0; i < frames.size(); ++i) { if (i) report << ','; report << frames[i]; }
        report << "]}";
    }
    std::cerr << "CADENCE_OBSERVER status=" << status << " gestures=" << gestures
              << " cycles=" << totalCycleEdges << " aliases=" << totalDuplicateEdges
              << " identity_unknown=" << runtimeIdentityUnknown << " error=" << error.substr(0,512) << std::endl;
    if (targetProcess) CloseHandle(targetProcess);
    targetProcess = nullptr;
    if (comInitialized) CoUninitialize();
    return status == "mixer_observation_collected_no_parameter_qualification" ? 0 : 3;
}
