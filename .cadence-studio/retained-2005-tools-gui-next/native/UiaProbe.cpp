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
#include "OwnedKeyboard.h"
#include "OwnedFileDialog.h"

using Microsoft::WRL::ComPtr;
using Clock = std::chrono::steady_clock;
static DWORD targetPid = 0;
static HANDLE targetProcess = nullptr;
static Clock::time_point deadline;
static std::vector<std::string> actions;
static std::vector<std::string> keyboardFrames;
static int keyboardGestureAttempts = 0;
static int f6GestureAttempts = 0, tabGestureAttempts = 0, rightGestureAttempts = 0, leftGestureAttempts = 0, downGestureAttempts = 0, returnGestureAttempts = 0;
static bool keyboardFailure = false;

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
    std::wstring name, id;
    int pid = 0, type = 0, depth = 0;
    BOOL enabled = FALSE, offscreen = TRUE, focused = FALSE;
};
static std::wstring controlLabel(const std::wstring& name)
{
    // MuseScore's accessible Name prepends the current panel to its focused
    // control (AccessibleItemInterface::text). Strip only known source labels.
    const std::vector<std::wstring> prefixes {
        L"Panneau Collections de sons, ", L"Panneau GeneralUser GS, ", L"Panneau MS Basic, ",
        L"Panneau Apprendre, ", L"Panneau Barre d'onglets d'apprentissage, ",
        L"Panneau Parcours musical hors ligne, ", L"Panneau Partitions, ",
        L"Panneau Dropdown, ", L"Dropdown panel, "
    };
    for (const auto& prefix : prefixes) if (name.rfind(prefix, 0) == 0) return name.substr(prefix.size());
    // Home menu appends source-owned direction help before the panel delimiter.
    // Strip that one known panel only, never an arbitrary suffix from another name.
    if (name.rfind(L"Panneau Menu Accueil", 0) == 0 || name.rfind(L"Home menu ", 0) == 0) {
        const auto delimiter = name.find(L", ");
        if (delimiter != std::wstring::npos) return name.substr(delimiter + 2);
    }
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
    element->get_CurrentHasKeyboardFocus(&node.focused);
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
                                       + ",\"title\":" + jsonQuoted(windowTitle(window))
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
        file << "{\"name\":" << jsonQuoted(node.name) << ",\"automation_id\":" << jsonQuoted(node.id)
             << ",\"control_type\":" << node.type << ",\"pid\":" << node.pid << ",\"depth\":" << node.depth
             << ",\"enabled\":" << (node.enabled ? "true" : "false") << ",\"offscreen\":" << (node.offscreen ? "true" : "false")
             << ",\"keyboard_focus\":" << (node.focused ? "true" : "false") << '}';
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
static void retainKeyboardFrame(const std::vector<Node>& nodes, const std::string& phase)
{
    if (keyboardFrames.size() >= 160) return;
    std::string frame = "{\"phase\":" + jsonQuoted(std::wstring(phase.begin(), phase.end())) + ",\"nodes\":[";
    size_t retained = 0;
    for (const Node& node : nodes) {
        if (retained >= 80) break;
        if (node.pid != static_cast<int>(targetPid) || node.name.empty()) continue;
        if (retained++) frame += ',';
        frame += "{\"name\":" + jsonQuoted(node.name) + ",\"control_type\":" + std::to_string(node.type)
                 + ",\"pid\":" + std::to_string(node.pid) + ",\"enabled\":" + (node.enabled ? "true" : "false")
                 + ",\"offscreen\":" + (node.offscreen ? "true" : "false")
                 + ",\"keyboard_focus\":" + (node.focused ? "true" : "false") + '}';
    }
    keyboardFrames.push_back(frame + "],\"retained_limit\":80}");
}
static bool sendNavigationKey(WORD key, const char* purpose)
{
    if (Clock::now() >= deadline || keyboardGestureAttempts >= 100) return false;
    if ((key == VK_F6 && f6GestureAttempts >= 35) || (key == VK_TAB && tabGestureAttempts >= 25)
        || (key == VK_RIGHT && rightGestureAttempts >= 15) || (key == VK_DOWN && downGestureAttempts >= 20)
        || (key == VK_LEFT && leftGestureAttempts >= 10) || (key == VK_RETURN && returnGestureAttempts >= 20)) return false;
    if (key == VK_F6) ++f6GestureAttempts;
    if (key == VK_TAB) ++tabGestureAttempts;
    if (key == VK_RIGHT) ++rightGestureAttempts;
    if (key == VK_LEFT) ++leftGestureAttempts;
    if (key == VK_DOWN) ++downGestureAttempts;
    if (key == VK_RETURN) ++returnGestureAttempts;
    ++keyboardGestureAttempts;
    const OwnedKeyResult result = SendOwnedKey(targetPid, targetProcess, mainWindow(), key);
    if (!result.sent) keyboardFailure = true;
    const char* label = key == VK_F6 ? "F6" : key == VK_TAB ? "Tab" : key == VK_RIGHT ? "Right" : key == VK_LEFT ? "Left" : key == VK_DOWN ? "Down" : key == VK_UP ? "Up" : key == VK_ESCAPE ? "Escape" : "Return";
    actions.push_back(std::string("{\"action\":\"owned_navigation_key\",\"purpose\":\"") + purpose
                      + "\",\"key\":\"" + label + "\",\"pid\":" + std::to_string(targetPid)
                      + ",\"foreground_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(result.foreground))
                      + ",\"focus_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(result.focus))
                      + ",\"input_count\":" + std::to_string(result.inputCount) + ",\"error\":" + std::to_string(result.error)
                      + ",\"sent\":" + (result.sent ? "true" : "false") + '}');
    return result.sent;
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
    actions.push_back(std::string("{\"action\":\"") + purpose + "\",\"name\":" + jsonQuoted(node->name)
                      + ",\"pid\":" + std::to_string(pid) + ",\"pattern\":\"" + pattern
                      + "\",\"hresult\":" + std::to_string(static_cast<long>(result)) + '}');
    return SUCCEEDED(result);
}
static bool focusAndTriggerLibrary(IUIAutomation* automation, const Node* node)
{
    if (!node || !alive() || Clock::now() >= deadline || !owned(mainWindow()) || !IsWindowEnabled(mainWindow())) return false;
    int pid = 0;
    if (FAILED(node->element->get_CurrentProcessId(&pid)) || pid != static_cast<int>(targetPid)) return false;
    const HRESULT focused = node->element->SetFocus();
    Sleep(100);
    ComPtr<IUIAutomationElement> current;
    BOOL same = FALSE;
    HRESULT compared = E_NOINTERFACE;
    if (SUCCEEDED(automation->GetFocusedElement(&current)) && current) compared = automation->CompareElements(current.Get(), node->element.Get(), &same);
    actions.push_back("{\"action\":\"focus_exact_library_for_keyboard\",\"name\":" + jsonQuoted(node->name)
                      + ",\"hresult\":" + std::to_string(static_cast<long>(focused))
                      + ",\"compare_elements_hresult\":" + std::to_string(static_cast<long>(compared))
                      + ",\"focused_element_matches\":" + (same ? "true" : "false") + '}');
    return SUCCEEDED(focused) && SUCCEEDED(compared) && same && sendNavigationKey(VK_RETURN, "trigger_exact_focused_library");
}
static bool triggerAlreadyFocusedLibrary(IUIAutomation* automation, const Node& node)
{
    const std::wstring label = controlLabel(node.name);
    if (node.pid != static_cast<int>(targetPid) || !node.enabled || node.offscreen
        || (node.type != UIA_RadioButtonControlTypeId && node.type != UIA_TabItemControlTypeId)
        || (label != L"Biblioth\u00e8que locale" && label != L"Local library")) return false;
    ComPtr<IUIAutomationElement> current;
    BOOL same = FALSE;
    HRESULT compared = E_NOINTERFACE;
    if (SUCCEEDED(automation->GetFocusedElement(&current)) && current) compared = automation->CompareElements(current.Get(), node.element.Get(), &same);
    actions.push_back("{\"action\":\"verify_already_focused_library\",\"name\":" + jsonQuoted(node.name)
                      + ",\"control_label\":" + jsonQuoted(label) + ",\"pid\":" + std::to_string(node.pid)
                      + ",\"compare_elements_hresult\":" + std::to_string(static_cast<long>(compared))
                      + ",\"focused_element_matches\":" + (same ? "true" : "false") + '}');
    return SUCCEEDED(compared) && same && sendNavigationKey(VK_RETURN, "trigger_observed_focused_library");
}
static bool triggerVerifiedFocusedButton(IUIAutomation* automation, const std::filesystem::path& output,
                                       const std::wstring& expectedLabel, const char* purpose)
{
    const Node node = focusedNode(automation);
    if (node.pid != static_cast<int>(targetPid) || node.type != UIA_ButtonControlTypeId || !node.enabled || node.offscreen
        || controlLabel(node.name) != expectedLabel) return false;
    auto nodes = snapshot(automation, output, L"tree-keyboard-before");
    retainKeyboardFrame(nodes, std::string("before_") + purpose);
    ComPtr<IUIAutomationElement> current;
    BOOL same = FALSE;
    HRESULT compared = E_NOINTERFACE;
    if (SUCCEEDED(automation->GetFocusedElement(&current)) && current) compared = automation->CompareElements(current.Get(), node.element.Get(), &same);
    actions.push_back("{\"action\":\"verify_focused_button_before_return\",\"purpose\":\"" + std::string(purpose)
                      + "\",\"name\":" + jsonQuoted(node.name) + ",\"pid\":" + std::to_string(node.pid)
                      + ",\"compare_elements_hresult\":" + std::to_string(static_cast<long>(compared))
                      + ",\"focused_element_matches\":" + (same ? "true" : "false") + '}');
    const bool sent = SUCCEEDED(compared) && same && sendNavigationKey(VK_RETURN, purpose);
    Sleep(250);
    nodes = snapshot(automation, output, L"tree-keyboard-after");
    retainKeyboardFrame(nodes, std::string("after_") + purpose);
    return sent;
}

#include "CloseExercise.inc"
#include "ToolsFlow.inc"
