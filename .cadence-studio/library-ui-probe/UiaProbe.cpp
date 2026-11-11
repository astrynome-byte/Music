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
        L"Panneau Partitions, ", L"Scores panel, ",
        L"Panneau Barre d'onglets des partitions, ", L"Scores tab bar panel, ",
        L"Panneau Biblioth\u00e8que locale, ", L"Biblioth\u00e8que locale panel, ", L"Local library panel, "
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
    if (keyboardFrames.size() >= 48) return;
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
    if (Clock::now() >= deadline || keyboardGestureAttempts >= 17) return false;
    if ((key == VK_F6 && f6GestureAttempts >= 6) || (key == VK_TAB && tabGestureAttempts >= 4)
        || (key == VK_RIGHT && rightGestureAttempts >= 3) || (key == VK_DOWN && downGestureAttempts >= 1)
        || (key == VK_LEFT && leftGestureAttempts >= 1)
        || (key == VK_RETURN && returnGestureAttempts >= 3)) return false;
    if (key == VK_F6) ++f6GestureAttempts;
    if (key == VK_TAB) ++tabGestureAttempts;
    if (key == VK_RIGHT) ++rightGestureAttempts;
    if (key == VK_LEFT) ++leftGestureAttempts;
    if (key == VK_DOWN) ++downGestureAttempts;
    if (key == VK_RETURN) ++returnGestureAttempts;
    ++keyboardGestureAttempts;
    const OwnedKeyResult result = SendOwnedKey(targetPid, targetProcess, mainWindow(), key);
    if (!result.sent) keyboardFailure = true;
    const char* label = key == VK_F6 ? "F6" : key == VK_TAB ? "Tab" : key == VK_RIGHT ? "Right" : key == VK_LEFT ? "Left" : key == VK_DOWN ? "Down" : "Return";
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
struct AddResult {
    bool dialogSelected = false, scoreAdded = false, favoriteRequested = false, favoriteLabelObserved = false;
    std::string status = "blocked_add_not_started";
};
static bool restoreLocalPanelAfterNativeDialog(IUIAutomation* automation, const std::filesystem::path& output)
{
    bool searchFocused = false;
    for (int attempt = 0; attempt < 4 && Clock::now() < deadline; ++attempt) {
        auto nodes = snapshot(automation, output, L"tree-keyboard-before");
        retainKeyboardFrame(nodes, "before_restore_section_after_native_dialog_" + std::to_string(attempt));
        const bool sent = sendNavigationKey(VK_F6, "restore_native_navigation_section_after_file_dialog");
        Sleep(300);
        nodes = snapshot(automation, output, L"tree-keyboard-after");
        retainKeyboardFrame(nodes, "after_restore_section_after_native_dialog_" + std::to_string(attempt));
        const Node node = focusedNode(automation);
        const std::wstring label = controlLabel(node.name);
        actions.push_back("{\"action\":\"observe_restored_navigation_focus\",\"name\":" + jsonQuoted(node.name)
                          + ",\"control_label\":" + jsonQuoted(label) + ",\"pid\":" + std::to_string(node.pid)
                          + ",\"control_type\":" + std::to_string(node.type) + '}');
        if (!sent || node.pid != static_cast<int>(targetPid)) return false;
        searchFocused = node.type == UIA_EditControlTypeId && node.enabled && !node.offscreen
                        && (label == L"Rechercher par titre, compositeur ou fichier" || label == L"Search recent scores"
                            || label == L"Rechercher les partitions r\u00e9centes");
        if (searchFocused) break;
    }
    if (!searchFocused) return false;
    for (int step = 0; step < 2; ++step) {
        auto nodes = snapshot(automation, output, L"tree-keyboard-before");
        retainKeyboardFrame(nodes, "before_restore_local_panel_tab_" + std::to_string(step));
        const bool sent = sendNavigationKey(VK_TAB, "restore_selected_library_tab_and_content_panel");
        Sleep(300);
        nodes = snapshot(automation, output, L"tree-keyboard-after");
        retainKeyboardFrame(nodes, "after_restore_local_panel_tab_" + std::to_string(step));
        const Node node = focusedNode(automation);
        const std::wstring label = controlLabel(node.name);
        const bool expected = step == 0
                              ? ((node.type == UIA_RadioButtonControlTypeId || node.type == UIA_TabItemControlTypeId)
                                 && (label == L"Biblioth\u00e8que locale" || label == L"Local library"))
                              : (node.type == UIA_ButtonControlTypeId && label == L"Ajouter des partitions\u2026");
        actions.push_back("{\"action\":\"verify_restored_local_panel_focus\",\"name\":" + jsonQuoted(node.name)
                          + ",\"step\":" + std::to_string(step) + ",\"expected\":" + (expected ? "true" : "false") + '}');
        if (!sent || !expected || node.pid != static_cast<int>(targetPid) || !node.enabled || node.offscreen) return false;
    }
    return true;
}
static AddResult exerciseAddAndFavorite(IUIAutomation* automation, const std::filesystem::path& output,
                                       const std::wstring& fixtureRoot, const std::wstring& fixturePath,
                                       const std::wstring& expectedTitle)
{
    AddResult result;
    if (deadline - Clock::now() < std::chrono::seconds(20)) { result.status = "blocked_add_time_budget"; return result; }
    if (!triggerVerifiedFocusedButton(automation, output, L"Ajouter des partitions\u2026", "open_add_scores_dialog")) {
        result.status = "blocked_focused_add_button_unavailable"; return result;
    }
    const OwnedFileSelectionResult selection = SelectOwnedScoreFile(automation, targetPid, targetProcess, mainWindow(), fixtureRoot,
                                                                   fixturePath, [&](const wchar_t* phase) {
        snapshot(automation, output, phase);
    });
    result.dialogSelected = selection.selected;
    actions.push_back("{\"action\":\"select_controlled_copy_in_owned_native_dialog\",\"path\":" + jsonQuoted(fixturePath)
                      + ",\"selected\":" + (selection.selected ? "true" : "false") + ",\"error\":" + std::to_string(selection.error)
                      + ",\"result_hresult\":" + std::to_string(static_cast<long>(selection.result))
                      + ",\"edit_discovery_hresult\":" + std::to_string(static_cast<long>(selection.editDiscovery))
                      + ",\"edit_name\":" + jsonQuoted(selection.editName) + ",\"edit_id\":" + jsonQuoted(selection.editAutomationId)
                      + ",\"value_pattern_hresult\":" + std::to_string(static_cast<long>(selection.valuePattern))
                      + ",\"set_value_hresult\":" + std::to_string(static_cast<long>(selection.setValue))
                      + ",\"read_value_hresult\":" + std::to_string(static_cast<long>(selection.readValue))
                      + ",\"value_verified\":" + (selection.valueVerified ? "true" : "false")
                      + ",\"verified_path\":" + jsonQuoted(selection.verifiedPath)
                      + ",\"button_name\":" + jsonQuoted(selection.buttonName) + ",\"button_id\":" + jsonQuoted(selection.buttonAutomationId)
                      + ",\"invoke_hresult\":" + std::to_string(static_cast<long>(selection.invoke))
                      + ",\"dialog_closed\":" + (selection.dialogClosed ? "true" : "false")
                      + ",\"main_enabled\":" + (selection.mainEnabled ? "true" : "false")
                      + ",\"diagnostic\":" + jsonQuoted(selection.diagnostic) + '}');
    if (!selection.selected) { snapshot(automation, output, L"file-dialog-blocked"); result.status = "blocked_native_add_dialog"; return result; }
    bool addReady = false;
    for (int attempt = 0; attempt < 12 && Clock::now() < deadline; ++attempt) {
        const Node node = focusedNode(automation);
        addReady = node.pid == static_cast<int>(targetPid) && node.type == UIA_ButtonControlTypeId && node.enabled && !node.offscreen
                   && controlLabel(node.name) == L"Ajouter des partitions\u2026";
        if (addReady) break;
        Sleep(250);
    }
    if (!addReady) { result.status = "blocked_add_focus_not_restored"; return result; }
    if (!restoreLocalPanelAfterNativeDialog(automation, output)) { result.status = "blocked_native_dialog_navigation_restore"; return result; }
    auto nodes = snapshot(automation, output, L"tree-keyboard-before");
    retainKeyboardFrame(nodes, "before_down_to_added_score");
    const bool down = sendNavigationKey(VK_DOWN, "focus_first_added_score_open_button");
    Sleep(300);
    nodes = snapshot(automation, output, L"tree-keyboard-after");
    retainKeyboardFrame(nodes, "after_down_to_added_score");
    const Node open = focusedNode(automation);
    result.scoreAdded = down && open.pid == static_cast<int>(targetPid) && open.type == UIA_ButtonControlTypeId
                        && open.enabled && !open.offscreen && controlLabel(open.name) == L"Ouvrir " + expectedTitle;
    actions.push_back("{\"action\":\"observe_added_score_open_control\",\"name\":" + jsonQuoted(open.name)
                      + ",\"pid\":" + std::to_string(open.pid) + ",\"expected_title\":" + jsonQuoted(expectedTitle)
                      + ",\"observed\":" + (result.scoreAdded ? "true" : "false") + '}');
    if (!result.scoreAdded) { result.status = "blocked_added_score_control_unavailable"; return result; }
    nodes = snapshot(automation, output, L"tree-keyboard-before");
    retainKeyboardFrame(nodes, "before_right_to_added_score_favorite");
    const bool right = sendNavigationKey(VK_RIGHT, "focus_added_score_favorite_button");
    Sleep(250);
    nodes = snapshot(automation, output, L"tree-keyboard-after");
    retainKeyboardFrame(nodes, "after_right_to_added_score_favorite");
    if (!right) { result.status = "blocked_favorite_navigation"; return result; }
    result.favoriteRequested = triggerVerifiedFocusedButton(automation, output, L"Ajouter aux favoris " + expectedTitle, "favorite_added_score");
    for (int attempt = 0; result.favoriteRequested && attempt < 8 && Clock::now() < deadline; ++attempt) {
        const Node favorite = focusedNode(automation);
        result.favoriteLabelObserved = favorite.pid == static_cast<int>(targetPid) && favorite.type == UIA_ButtonControlTypeId
                                       && favorite.enabled && !favorite.offscreen && controlLabel(favorite.name) == L"Retirer des favoris " + expectedTitle;
        if (result.favoriteLabelObserved) break;
        Sleep(200);
    }
    result.status = result.favoriteRequested ? "score_added_favorite_action_delivered_requires_catalog_check" : "blocked_favorite_control_unavailable";
    return result;
}

#include "VerifyExistingScore.inc"

int wmain(int argc, wchar_t** argv)
{
    std::filesystem::path output;
    std::wstring fixtureRoot, fixturePath, expectedTitle;
    bool verifyExisting = false;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (std::wstring(argv[i]) == L"--pid") targetPid = wcstoul(argv[i + 1], nullptr, 10);
        else if (std::wstring(argv[i]) == L"--output") output = argv[i + 1];
        else if (std::wstring(argv[i]) == L"--fixture-root") fixtureRoot = argv[i + 1];
        else if (std::wstring(argv[i]) == L"--add-fixture") { if (!fixturePath.empty()) return 1; fixturePath = argv[i + 1]; }
        else if (std::wstring(argv[i]) == L"--verify-fixture") { if (!fixturePath.empty()) return 1; fixturePath = argv[i + 1]; verifyExisting = true; }
        else if (std::wstring(argv[i]) == L"--expected-title") expectedTitle = argv[i + 1];
        else return 1;
    }
    if (!targetPid || output.empty() || !std::filesystem::is_directory(output)) return 1;
    if ((!fixturePath.empty() || !fixtureRoot.empty() || !expectedTitle.empty())
        && (fixturePath.empty() || fixtureRoot.empty() || expectedTitle.empty())) return 1;
    targetProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, targetPid);
    if (!alive()) return 1;
    deadline = Clock::now() + std::chrono::seconds(55);
    std::string status = "blocked_uia_unavailable";
    bool contentObserved = false;
    bool contentObservedFromFocusedElement = false;
    bool navigationReady = false;
    int readinessPolls = 0;
    AddResult addition;
    ExistingScoreResult existing;
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
            int keySteps = 0, sectionKeys = 0, panelKeys = 0, rightKeys = 0;
            while (navigationReady && alive() && Clock::now() < deadline) {
                if (closeIntroductionOnly()) Sleep(400);
                nodes = snapshot(automation.Get(), output, L"tree-navigation-ready");
                if (const Node* library = find(nodes, libraryNames)) {
                    activatedLibrary = invokeSemantic(library, "activate_local_library");
                    if (!activatedLibrary && keySteps < 12) {
                        retainKeyboardFrame(nodes, "before_exact_library_focus");
                        activatedLibrary = focusAndTriggerLibrary(automation.Get(), library);
                        Sleep(250);
                        nodes = snapshot(automation.Get(), output, L"tree-keyboard-after");
                        retainKeyboardFrame(nodes, "after_exact_library_focus");
                    }
                    if (activatedLibrary) break;
                } else if (!activatedScores && invokeSemantic(find(nodes, scoreNames), "activate_scores")) {
                    activatedScores = true;
                    nodes = snapshot(automation.Get(), output, L"tree-after-scores");
                }
                if (keyboardFailure || keySteps >= 12 || keyboardGestureAttempts >= 12) break;
                const Node focused = focusedNode(automation.Get());
                const std::wstring focusedName = controlLabel(focused.name);
                const int focusedType = focused.type, focusedPid = focused.pid;
                actions.push_back("{\"action\":\"observe_navigation_focus\",\"name\":" + jsonQuoted(focusedName)
                                  + ",\"original_name\":" + jsonQuoted(focused.name)
                                  + ",\"control_type\":" + std::to_string(focusedType) + ",\"pid\":" + std::to_string(focusedPid) + '}');
                // F6 needs an owned Win32 focus (checked by SendOwnedKey), not
                // an already exposed UIA child. Other-process UIA focus stops
                // all keys; an unavailable UIA focus permits only F6 discovery.
                if (focusedPid != 0 && focusedPid != static_cast<int>(targetPid)) break;
                if (focusedPid == static_cast<int>(targetPid)
                    && (focusedName == L"Biblioth\u00e8que locale" || focusedName == L"Local library")) {
                    nodes = snapshot(automation.Get(), output, L"tree-keyboard-before");
                    retainKeyboardFrame(nodes, "before_observed_focused_library_return");
                    activatedLibrary = triggerAlreadyFocusedLibrary(automation.Get(), focused);
                    Sleep(300);
                    nodes = snapshot(automation.Get(), output, L"tree-keyboard-after");
                    retainKeyboardFrame(nodes, "after_observed_focused_library_return");
                    break;
                }
                WORD key = VK_F6;
                if (focusedPid == static_cast<int>(targetPid) && focusedType == UIA_EditControlTypeId
                    && (focusedName == L"Rechercher" || focusedName == L"Search"
                        || focusedName == L"Rechercher par titre, compositeur ou fichier"
                        || focusedName == L"Rechercher les partitions r\u00e9centes" || focusedName == L"Search recent scores")) {
                    if (panelKeys++ >= 2) break;
                    key = VK_TAB;
                } else if (focusedPid == static_cast<int>(targetPid)
                           && (focusedType == UIA_TabItemControlTypeId || focusedType == UIA_RadioButtonControlTypeId)
                           && (focusedName == L"Nouvelle et r\u00e9cente" || focusedName == L"New & recent"
                               || focusedName == L"Mes partitions en ligne" || focusedName == L"My online scores")) {
                    if (rightKeys++ >= 2) break;
                    key = VK_RIGHT;
                } else if (sectionKeys++ >= 6) break;
                nodes = snapshot(automation.Get(), output, L"tree-keyboard-before");
                retainKeyboardFrame(nodes, "before_navigation_key_" + std::to_string(keySteps));
                const bool sent = sendNavigationKey(key, "navigate_native_musescore_sections_or_panels");
                ++keySteps;
                Sleep(300);
                nodes = snapshot(automation.Get(), output, L"tree-keyboard-after");
                retainKeyboardFrame(nodes, "after_navigation_key_" + std::to_string(keySteps));
                if (!sent) break;
            }
            if (activatedLibrary) Sleep(750);
            bool movedToLibraryPanel = false;
            for (int attempt = 0; attempt < 8 && Clock::now() < deadline; ++attempt) {
                nodes = snapshot(automation.Get(), output, L"tree-final");
                const Node* add = find(nodes, { L"Ajouter des partitions\u2026", L"Ajouter des partitions...", L"Add scores\u2026" });
                const Node focused = focusedNode(automation.Get());
                const std::wstring label = controlLabel(focused.name);
                const bool focusedAdd = focused.pid == static_cast<int>(targetPid) && focused.enabled && !focused.offscreen
                                        && focused.type == UIA_ButtonControlTypeId
                                        && (label == L"Ajouter des partitions\u2026" || label == L"Ajouter des partitions..." || label == L"Add scores\u2026");
                contentObservedFromFocusedElement = activatedLibrary && focusedAdd;
                contentObserved = activatedLibrary && (add != nullptr || focusedAdd);
                if (!contentObserved && activatedLibrary && !movedToLibraryPanel
                    && focused.pid == static_cast<int>(targetPid) && focused.enabled && !focused.offscreen
                    && (label == L"Biblioth\u00e8que locale" || label == L"Local library")
                    && (focused.type == UIA_RadioButtonControlTypeId || focused.type == UIA_TabItemControlTypeId)) {
                    retainKeyboardFrame(nodes, "before_tab_to_local_library_panel");
                    const bool sent = sendNavigationKey(VK_TAB, "navigate_from_selected_library_tab_to_its_panel");
                    movedToLibraryPanel = true;
                    Sleep(300);
                    nodes = snapshot(automation.Get(), output, L"tree-keyboard-after");
                    retainKeyboardFrame(nodes, "after_tab_to_local_library_panel");
                    if (!sent) break;
                    continue;
                }
                actions.push_back("{\"action\":\"observe_library_content_focus\",\"name\":" + jsonQuoted(focused.name)
                                  + ",\"control_label\":" + jsonQuoted(label) + ",\"pid\":" + std::to_string(focused.pid)
                                  + ",\"control_type\":" + std::to_string(focused.type) + ",\"enabled\":" + (focused.enabled ? "true" : "false")
                                  + ",\"offscreen\":" + (focused.offscreen ? "true" : "false")
                                  + ",\"add_button_observed\":" + (focusedAdd ? "true" : "false") + '}');
                if (contentObserved || !activatedLibrary) break;
                Sleep(400);
            }
            status = contentObserved ? "library_tab_active_and_add_control_observed" : "blocked_library_controls_or_semantic_action_unavailable";
            if (!contentObserved && owned(mainWindow()) && !IsWindowEnabled(mainWindow())) status = "blocked_owned_modal_remaining_after_introduction";
            if (!contentObserved && Clock::now() > deadline) status = navigationReady ? "blocked_uia_inspection_deadline" : "blocked_semantic_navigation_not_ready_before_deadline";
            if (contentObserved && verifyExisting) {
                existing = VerifyFavoriteAndOpen(automation.Get(), output, expectedTitle, fixturePath);
                status = existing.status;
            } else if (contentObserved && !fixturePath.empty()) {
                addition = exerciseAddAndFavorite(automation.Get(), output, fixtureRoot, fixturePath, expectedTitle);
                status = addition.status;
            }
        }
        automation.Reset(); bounded.Reset(); CoUninitialize();
    }
    std::ofstream result(output / L"uia-report.json", std::ios::binary);
    result << "{\"scope\":" << jsonQuoted(verifyExisting
              ? L"Owned PID library replay and opening of the controlled score copy; no note editing or musical file writes"
              : L"Owned PID library navigation and optional controlled-copy Add/favorite; no score editor opened or musical file writes") << ",\"pid\":"
           << targetPid << ",\"status\":\"" << status << "\",\"com_activation_hresult\":" << static_cast<long>(activated)
           << ",\"library_content_observed\":" << (contentObserved ? "true" : "false")
           << ",\"library_content_observed_via_focused_UIA_element\":" << (contentObservedFromFocusedElement ? "true" : "false")
           << ",\"add_requested\":" << (!fixturePath.empty() && !verifyExisting ? "true" : "false")
           << ",\"verify_existing_requested\":" << (verifyExisting ? "true" : "false")
           << ",\"favorite_restored_control_observed\":" << (existing.favoriteRestored ? "true" : "false")
           << ",\"score_open_requested\":" << (existing.openRequested ? "true" : "false")
           << ",\"score_editor_title_observed\":" << (existing.editorTitleObserved ? "true" : "false")
           << ",\"score_editor_title\":" << jsonQuoted(existing.observedTitle)
           << ",\"owned_file_dialog_selected_copy\":" << (addition.dialogSelected ? "true" : "false")
           << ",\"score_added_control_observed\":" << (addition.scoreAdded ? "true" : "false")
           << ",\"favorite_action_delivered\":" << (addition.favoriteRequested ? "true" : "false")
           << ",\"favorite_remove_label_observed\":" << (addition.favoriteLabelObserved ? "true" : "false")
           << ",\"semantic_navigation_ready\":" << (navigationReady ? "true" : "false")
           << ",\"readiness_polls\":" << readinessPolls << ",\"global_deadline_seconds\":55,\"actions\":[";
    for (size_t i = 0; i < actions.size(); ++i) { if (i) result << ','; result << actions[i]; }
    result << "],\"keyboard_gestures_allowed\":true,\"keyboard_gesture_attempts\":" << keyboardGestureAttempts
           << ",\"keyboard_failure_stops_sequence\":" << (keyboardFailure ? "true" : "false") << ",\"keyboard_frames\":[";
    for (size_t i = 0; i < keyboardFrames.size(); ++i) { if (i) result << ','; result << keyboardFrames[i]; }
    result << "],\"windows\":[";
    bool firstWindow = true;
    for (HWND window : windows()) {
        if (!firstWindow) result << ',';
        firstWindow = false;
        result << "{\"handle\":" << reinterpret_cast<std::uintptr_t>(window) << ",\"title\":" << jsonQuoted(windowTitle(window))
               << ",\"owner_handle\":" << reinterpret_cast<std::uintptr_t>(GetWindow(window, GW_OWNER))
               << ",\"pid\":" << targetPid << ",\"enabled\":" << (IsWindowEnabled(window) ? "true" : "false") << '}';
    }
    result << "],\"score_editing_tested\":false,\"favorites_tested\":false,\"listening_tested\":false}";
    CloseHandle(targetProcess);
    return contentObserved && (verifyExisting ? (existing.favoriteRestored && existing.openRequested && existing.editorTitleObserved)
                              : (fixturePath.empty() || (addition.scoreAdded && addition.favoriteRequested))) ? 0 : 2;
}
