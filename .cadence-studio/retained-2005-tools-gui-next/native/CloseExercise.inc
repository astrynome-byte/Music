// SPDX-License-Identifier: GPL-3.0-only
// Close only the owned imported exercise, never save it or navigate an unknown dialog.
static bool closeProcessExited(DWORD& code)
{
    return targetProcess && WaitForSingleObject(targetProcess, 0) == WAIT_OBJECT_0
        && GetExitCodeProcess(targetProcess, &code);
}
static bool exerciseCaption(const std::wstring& caption)
{
    return caption.find(L"pulsation") != std::wstring::npos || caption.find(L"Garder la pulsation") != std::wstring::npos;
}
static std::wstring closeWindowClass(HWND window)
{
    wchar_t buffer[256] = {};
    GetClassNameW(window, buffer, 256);
    return buffer;
}
static bool modalOfExercise(HWND modal, HWND exercise)
{
    if (!owned(modal) || !owned(exercise) || modal == exercise || !IsWindowVisible(modal)
        || !IsWindowEnabled(modal) || IsWindowEnabled(exercise)) return false;
    HWND owner = GetWindow(modal, GW_OWNER);
    for (int depth = 0; owner && depth < 8; ++depth) {
        if (!owned(owner)) return false;
        if (owner == exercise) return true;
        owner = GetWindow(owner, GW_OWNER);
    }
    return false;
}
static std::wstring discardLabel(const std::wstring& raw)
{
    const std::wstring frenchPrefix = L"Panneau Attention, ", englishPrefix = L"Warning panel, ";
    if (raw.rfind(frenchPrefix, 0) == 0) return raw.substr(frenchPrefix.size());
    if (raw.rfind(englishPrefix, 0) == 0) return raw.substr(englishPrefix.size());
    return raw;
}
static bool exactDiscardNode(const Node& node)
{
    const auto label = discardLabel(node.name);
    return node.element && node.pid == static_cast<int>(targetPid) && node.type == UIA_ButtonControlTypeId
        && node.enabled && !node.offscreen
        && (label == L"Ne pas enregistrer" || label == L"Don\u2019t save" || label == L"Don't save");
}
static bool currentDiscardNode(const Node& node)
{
    if (!exactDiscardNode(node) || !alive()) return false;
    Node current = node;
    BSTR name = nullptr;
    if (FAILED(node.element->get_CurrentName(&name))) { SysFreeString(name); return false; }
    current.name = text(name);
    return SUCCEEDED(node.element->get_CurrentProcessId(&current.pid))
        && SUCCEEDED(node.element->get_CurrentControlType(&current.type))
        && SUCCEEDED(node.element->get_CurrentIsEnabled(&current.enabled))
        && SUCCEEDED(node.element->get_CurrentIsOffscreen(&current.offscreen)) && exactDiscardNode(current);
}
static bool elementBelowModal(IUIAutomation* automation, IUIAutomationElement* element, IUIAutomationElement* root)
{
    ComPtr<IUIAutomationTreeWalker> walker;
    if (FAILED(automation->get_RawViewWalker(&walker))) return false;
    ComPtr<IUIAutomationElement> current = element;
    for (int depth = 0; current && depth < 20 && Clock::now() < deadline; ++depth) {
        BOOL same = FALSE;
        if (FAILED(automation->CompareElements(current.Get(), root, &same))) return false;
        if (same) return true;
        ComPtr<IUIAutomationElement> parent;
        if (FAILED(walker->GetParentElement(current.Get(), &parent))) return false;
        current = parent;
    }
    return false;
}

// Identity is the real UIA element identity, never a name, AutomationId or proxy address.
// CompareElements is already used by the retained client; no new SDK dependency.
struct ModalReadState {
    IUIAutomation* automation = nullptr;
    HWND modal = nullptr, exercise = nullptr;
    std::vector<ComPtr<IUIAutomationElement>> identities;
    std::vector<bool> expanded;
    std::vector<Node> nodes;
    size_t candidates = 0, comparisons = 0, repeated = 0, siblingCycles = 0, ancestorCycles = 0;
    bool complete = true, deadlineReached = false, limitReached = false;
    const char* error = "none";
    bool ready() {
        if (!complete) return false;
        if (Clock::now() >= deadline) { complete = false; deadlineReached = true; error = "deadline"; return false; }
        if (!modalOfExercise(modal, exercise)) { complete = false; error = "owned_modal_changed"; return false; }
        return true;
    }
    void fail(const char* reason) { complete = false; error = reason; }
    int identity(IUIAutomationElement* element) {
        if (!element || !ready()) return -1;
        if (candidates >= 1200) { limitReached = true; fail("candidate_limit"); return -1; }
        ++candidates;
        for (size_t i = 0; i < identities.size(); ++i) {
            if (!ready()) return -1;
            BOOL same = FALSE;
            ++comparisons;
            if (FAILED(automation->CompareElements(element, identities[i].Get(), &same))) {
                fail("identity_comparison_failed"); return -1;
            }
            if (same) return static_cast<int>(i);
        }
        identities.emplace_back(element);
        expanded.push_back(false);
        return static_cast<int>(identities.size() - 1);
    }
};
static void readModalElement(IUIAutomationTreeWalker* walker, IUIAutomationElement* element,
                             int identity, int depth, ModalReadState& state, std::vector<int> ancestors = {})
{
    if (identity < 0 || !state.ready()) return;
    if (state.expanded[static_cast<size_t>(identity)]) { ++state.repeated; return; }
    if (state.nodes.size() >= 1200 || depth > 18) { state.limitReached = true; state.fail("node_or_depth_limit"); return; }
    state.expanded[static_cast<size_t>(identity)] = true;
    ancestors.push_back(identity);
    Node node; node.element = element; node.depth = depth;
    auto read = [&](auto operation) {
        if (!state.ready()) return false;
        if (FAILED(operation())) { state.fail("uia_property_read_failed"); return false; }
        return true;
    };
    UIA_HWND nativeWindow = {};
    if (!read([&] { return element->get_CurrentProcessId(&node.pid); })
        || !read([&] { return element->get_CurrentNativeWindowHandle(&nativeWindow); })) return;
    if (node.pid != static_cast<int>(targetPid)) { state.fail("foreign_modal_element_pid"); return; }
    const HWND native = reinterpret_cast<HWND>(nativeWindow);
    if (native && (!owned(native) || GetAncestor(native, GA_ROOT) != state.modal)) {
        state.fail("element_hwnd_outside_modal"); return;
    }
    BSTR value = nullptr;
    bool ok = read([&] { return element->get_CurrentName(&value); });
    node.name = text(value); value = nullptr;
    if (!ok) return;
    ok = read([&] { return element->get_CurrentAutomationId(&value); });
    node.id = text(value); value = nullptr;
    if (!ok || !read([&] { return element->get_CurrentControlType(&node.type); })
        || !read([&] { return element->get_CurrentIsEnabled(&node.enabled); })
        || !read([&] { return element->get_CurrentIsOffscreen(&node.offscreen); })
        || !read([&] { return element->get_CurrentHasKeyboardFocus(&node.focused); })) return;
    state.nodes.push_back(node);
    // Do not issue a first-child call at the existing depth cap. A partial read
    // may never authorize a discard that could hide another exact candidate.
    if (depth == 18) { state.limitReached = true; state.fail("depth_limit"); return; }
    ComPtr<IUIAutomationElement> child;
    if (!state.ready()) return;
    if (FAILED(walker->GetFirstChildElement(element, &child))) { state.fail("first_child_failed"); return; }
    std::vector<int> siblingIdentities;
    while (child && state.ready()) {
        const int childIdentity = state.identity(child.Get());
        if (childIdentity < 0) return;
        // An ancestor returned as a child is not a sibling cursor: asking for
        // its next sibling could escape this modal. Refuse an incomplete view.
        if (std::find(ancestors.begin(), ancestors.end(), childIdentity) != ancestors.end()) {
            ++state.ancestorCycles; state.fail("ancestor_reference_in_modal_view"); return;
        }
        if (std::find(siblingIdentities.begin(), siblingIdentities.end(), childIdentity) != siblingIdentities.end()) {
            ++state.siblingCycles; break;
        }
        siblingIdentities.push_back(childIdentity);
        ComPtr<IUIAutomationElement> checkedParent;
        BOOL parentMatches = FALSE;
        if (!state.ready()) return;
        if (FAILED(walker->GetParentElement(child.Get(), &checkedParent)) || !checkedParent) {
            state.fail("inconsistent_modal_child_parent"); return;
        }
        if (!state.ready()) return;
        ++state.comparisons;
        if (FAILED(state.automation->CompareElements(checkedParent.Get(), element, &parentMatches)) || !parentMatches) {
            state.fail("inconsistent_modal_child_parent"); return;
        }
        readModalElement(walker, child.Get(), childIdentity, depth + 1, state, ancestors);
        if (!state.ready()) return;
        ComPtr<IUIAutomationElement> sibling;
        if (FAILED(walker->GetNextSiblingElement(child.Get(), &sibling))) { state.fail("next_sibling_failed"); return; }
        child = sibling;
    }
}
static ModalReadState readOwnedModal(IUIAutomation* automation, IUIAutomationTreeWalker* walker,
                                    IUIAutomationElement* root, HWND modal, HWND exercise)
{
    ModalReadState state; state.automation = automation; state.modal = modal; state.exercise = exercise;
    UIA_HWND rootWindow = {};
    int rootPid = 0;
    if (!root) { state.fail("modal_root_absent"); return state; }
    if (!state.ready()) return state;
    if (FAILED(root->get_CurrentNativeWindowHandle(&rootWindow)) || reinterpret_cast<HWND>(rootWindow) != modal) {
        state.fail("modal_root_hwnd_or_pid_unverified"); return state;
    }
    if (!state.ready()) return state;
    if (FAILED(root->get_CurrentProcessId(&rootPid)) || rootPid != static_cast<int>(targetPid)) {
        state.fail("modal_root_hwnd_or_pid_unverified"); return state;
    }
    const int identity = state.identity(root);
    readModalElement(walker, root, identity, 0, state);
    state.ready(); // Also account for the final synchronous UIA call returning after the deadline.
    return state;
}
static void saveModalRead(const std::filesystem::path& output, const wchar_t* phase, const ModalReadState& state)
{
    std::ofstream file(output / (std::wstring(phase) + L".json"), std::ios::binary);
    file << "{\"pid\":" << targetPid << ",\"bounded\":true,\"scope\":\"verified_owned_modal_only\",\"max_nodes\":1200,\"max_depth\":18"
        << ",\"source_hwnd\":" << reinterpret_cast<std::uintptr_t>(state.modal)
        << ",\"complete\":" << (state.complete ? "true" : "false") << ",\"error\":\"" << state.error << '"'
        << ",\"deadline_reached\":" << (state.deadlineReached ? "true" : "false")
        << ",\"node_limit_reached\":" << (state.limitReached ? "true" : "false")
        << ",\"candidate_reads\":" << state.candidates << ",\"identity_comparisons\":" << state.comparisons
        << ",\"unique_identities\":" << state.identities.size() << ",\"repeated_references_skipped\":" << state.repeated
        << ",\"sibling_cycles_stopped\":" << state.siblingCycles
        << ",\"ancestor_cycles_stopped\":" << state.ancestorCycles << ",\"nodes\":[";
    bool first = true;
    for (const Node& node : state.nodes) {
        if (!first) file << ','; first = false;
        file << "{\"name\":" << jsonQuoted(node.name) << ",\"automation_id\":" << jsonQuoted(node.id)
            << ",\"control_type\":" << node.type << ",\"pid\":" << node.pid << ",\"depth\":" << node.depth
            << ",\"enabled\":" << (node.enabled ? "true" : "false") << ",\"offscreen\":" << (node.offscreen ? "true" : "false")
            << ",\"keyboard_focus\":" << (node.focused ? "true" : "false") << '}';
    }
    file << "]}";
}

static int closeOwnedExercise(const std::filesystem::path& output)
{
    deadline = Clock::now() + std::chrono::seconds(25);
    bool requested = false, observed = false, delivered = false, exited = false, modalSeen = false, exposureAttempted = false, exposureDelivered = false;
    DWORD exitCode = STILL_ACTIVE;
    std::wstring initialCaption, initialClass, observedModalCaption, observedDiscardLabel;
    std::string method = "none", reason = "blocked_com_or_owned_exercise_unavailable";
    HWND exercise = mainWindow();
    initialCaption = windowTitle(exercise); initialClass = closeWindowClass(exercise);
    HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED), activated = initialized;
    if (SUCCEEDED(initialized)) {
        ComPtr<IUIAutomation> automation;
        activated = CoCreateInstance(__uuidof(CUIAutomation8), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        if (FAILED(activated)) activated = CoCreateInstance(__uuidof(CUIAutomation), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        ComPtr<IUIAutomation2> bounded;
        if (SUCCEEDED(activated) && SUCCEEDED(automation.As(&bounded))
            && SUCCEEDED(bounded->put_ConnectionTimeout(800)) && SUCCEEDED(bounded->put_TransactionTimeout(1000))
            && owned(exercise) && IsWindowVisible(exercise) && IsWindowEnabled(exercise) && !GetWindow(exercise, GW_OWNER)
            && exerciseCaption(initialCaption) && initialClass.rfind(L"Qt", 0) == 0 && initialClass.find(L"QWindow") != std::wstring::npos) {
            snapshot(automation.Get(), output, L"tree-before-exercise-close");
            // Re-read the same frame immediately before the only close message.
            requested = owned(exercise) && IsWindowEnabled(exercise) && windowTitle(exercise) == initialCaption
                && PostMessageW(exercise, WM_CLOSE, 0, 0);
            reason = requested ? "blocked_exit_or_exact_discard_dialog_not_observed" : "blocked_owned_wm_close_not_posted";
            while (requested && Clock::now() < deadline) {
                if (closeProcessExited(exitCode)) { exited = true; break; }
                if (!alive() || !owned(exercise)) break;
                HWND modal = nullptr;
                bool ambiguous = false;
                for (HWND candidate : windows()) {
                    if (!modalOfExercise(candidate, exercise)) continue;
                    if (modal) { ambiguous = true; break; }
                    modal = candidate;
                }
                if (ambiguous) { modalSeen = true; reason = "blocked_ambiguous_owned_modal"; break; }
                if (!modal) { Sleep(120); continue; }
                modalSeen = true;
                observedModalCaption = windowTitle(modal);
                ComPtr<IUIAutomationElement> modalRoot;
                ComPtr<IUIAutomationTreeWalker> walker;
                if (FAILED(automation->ElementFromHandle(modal, &modalRoot)) || !modalRoot
                    || FAILED(automation->get_RawViewWalker(&walker))) { reason = "blocked_owned_modal_provider"; break; }
                const auto modalRead = readOwnedModal(automation.Get(), walker.Get(), modalRoot.Get(), modal, exercise);
                const auto& nodes = modalRead.nodes;
                retainKeyboardFrame(nodes, "exact_owned_discard_dialog");
                saveModalRead(output, L"tree-owned-discard-dialog", modalRead);
                if (!modalRead.complete || Clock::now() >= deadline) { reason = "blocked_owned_modal_read_incomplete"; break; }
                const Node* discard = nullptr;
                for (const auto& node : nodes) {
                    if (!exactDiscardNode(node)) continue;
                    if (discard) { ambiguous = true; break; }
                    discard = &node;
                }
                if (ambiguous) { reason = "blocked_ambiguous_discard_buttons"; break; }
                if (!discard) {
                    reason = "blocked_exact_discard_button_unavailable";
                    if (!exposureAttempted) {
                        exposureAttempted = true;
                        const std::wstring modalClass = closeWindowClass(modal);
                        const HWND foreground = GetForegroundWindow();
                        DWORD modalPid = 0;
                        const DWORD thread = GetWindowThreadProcessId(modal, &modalPid);
                        GUITHREADINFO focusInfo {}; focusInfo.cbSize = static_cast<DWORD>(sizeof(focusInfo));
                        const bool focusRead = thread && GetGUIThreadInfo(thread, &focusInfo);
                        const bool guarded = modalOfExercise(modal, exercise) && modalPid == targetPid
                            && modalClass.rfind(L"Qt", 0) == 0 && modalClass.find(L"QWindow") != std::wstring::npos
                            && foreground == modal && focusRead && focusInfo.hwndFocus
                            && GetAncestor(focusInfo.hwndFocus, GA_ROOT) == modal;
                        OwnedKeyResult key;
                        if (guarded) key = SendOwnedKey(targetPid, targetProcess, modal, VK_TAB);
                        exposureDelivered = guarded && key.sent;
                        actions.push_back("{\"action\":\"single_owned_modal_exposure_tab\",\"pid\":" + std::to_string(modalPid)
                            + ",\"class_name\":" + jsonQuoted(modalClass)
                            + ",\"main_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(exercise))
                            + ",\"modal_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(modal))
                            + ",\"foreground_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(foreground))
                            + ",\"focus_handle\":" + std::to_string(reinterpret_cast<std::uintptr_t>(focusInfo.hwndFocus))
                            + ",\"guards_verified\":" + (guarded ? "true" : "false")
                            + ",\"input_count\":" + std::to_string(key.inputCount) + ",\"error\":" + std::to_string(key.error)
                            + ",\"delivered\":" + (exposureDelivered ? "true" : "false") + "}");
                        if (!exposureDelivered) { reason = "blocked_owned_modal_exposure_guard_or_delivery"; break; }
                        Sleep(180);
                        const auto afterTabRead = readOwnedModal(automation.Get(), walker.Get(), modalRoot.Get(), modal, exercise);
                        saveModalRead(output, L"tree-after-single-modal-tab", afterTabRead);
                        if (!afterTabRead.complete) { reason = "blocked_owned_modal_read_incomplete_after_tab"; break; }
                    } else Sleep(120);
                    continue;
                }
                observed = true; observedDiscardLabel = discardLabel(discard->name);
                if (!modalOfExercise(modal, exercise) || !currentDiscardNode(*discard)
                    || !elementBelowModal(automation.Get(), discard->element.Get(), modalRoot.Get())) {
                    reason = "blocked_discard_identity_or_ownership_changed"; break;
                }
                ComPtr<IUIAutomationInvokePattern> invoke;
                if (SUCCEEDED(discard->element->GetCurrentPatternAs(UIA_InvokePatternId, IID_PPV_ARGS(&invoke)))) {
                    method = "Invoke";
                    if (modalOfExercise(modal, exercise) && currentDiscardNode(*discard)) delivered = SUCCEEDED(invoke->Invoke());
                } else {
                    // Main is disabled by this modal. Pass the verified enabled
                    // owned modal to the unchanged keyboard guard, never the main.
                    method = "SetFocus+OwnedReturn";
                    const HRESULT focused = discard->element->SetFocus();
                    Sleep(100);
                    const Node current = focusedNode(automation.Get());
                    BOOL same = FALSE;
                    if (SUCCEEDED(focused) && current.element && exactDiscardNode(current)
                        && SUCCEEDED(automation->CompareElements(current.element.Get(), discard->element.Get(), &same)) && same
                        && modalOfExercise(modal, exercise) && GetForegroundWindow() == modal && IsWindowEnabled(modal)
                        && currentDiscardNode(*discard) && elementBelowModal(automation.Get(), current.element.Get(), modalRoot.Get())) {
                        const OwnedKeyResult key = SendOwnedKey(targetPid, targetProcess, modal, VK_RETURN);
                        delivered = key.sent;
                        actions.push_back("{\"action\":\"owned_exact_discard_return\",\"sent\":" + std::string(key.sent ? "true" : "false")
                            + ",\"error\":" + std::to_string(key.error) + ",\"input_count\":" + std::to_string(key.inputCount) + '}');
                    }
                }
                reason = delivered ? "blocked_exit_after_discard" : "blocked_exact_discard_delivery";
                // Only one semantic discard attempt. Unknown/new dialogs and
                // failure stay blocked; never follow with Save, Cancel or Tab.
                while (delivered && Clock::now() < deadline) {
                    if (closeProcessExited(exitCode)) { exited = true; break; }
                    Sleep(100);
                }
                break;
            }
        }
        bounded.Reset(); automation.Reset(); CoUninitialize();
    }
    if (!exited) exited = closeProcessExited(exitCode);
    const bool passed = requested && exited && exitCode == 0 && (!modalSeen || (observed && delivered));
    if (passed) reason = "closed_owned_exercise_exit0";
    std::ofstream report(output / L"close-report.json", std::ios::binary);
    report << "{\"schema_version\":1,\"pid\":" << targetPid << ",\"status\":\"" << reason
        << "\",\"close_requested\":" << (requested ? "true" : "false")
        << ",\"discard_control_observed\":" << (observed ? "true" : "false")
        << ",\"owned_modal_observed\":" << (modalSeen ? "true" : "false")
        << ",\"discard_delivered\":" << (delivered ? "true" : "false")
        << ",\"app_exit_observed\":" << (exited ? "true" : "false") << ",\"exit_code\":";
    if (exited) report << exitCode; else report << "null";
    report << ",\"initial_caption\":" << jsonQuoted(initialCaption) << ",\"initial_window_class\":" << jsonQuoted(initialClass)
        << ",\"modal_caption\":" << jsonQuoted(observedModalCaption) << ",\"discard_label\":" << jsonQuoted(observedDiscardLabel)
        << ",\"discard_method\":\"" << method << "\",\"deadline_seconds\":25,\"save_requested\":false"
        << ",\"discard_exposure_tab_attempted\":" << (exposureAttempted ? "true" : "false")
        << ",\"discard_exposure_tab_delivered\":" << (exposureDelivered ? "true" : "false") << ",\"actions\":[";
    for (size_t index = 0; index < actions.size(); ++index) { if (index) report << ','; report << actions[index]; }
    report << "],\"keyboard_frames\":[";
    for (size_t index = 0; index < keyboardFrames.size(); ++index) { if (index) report << ','; report << keyboardFrames[index]; }
    report << "]}\n";
    CloseHandle(targetProcess);
    return passed ? 0 : 2;
}
