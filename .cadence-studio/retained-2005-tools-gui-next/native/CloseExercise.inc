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
static int closeOwnedExercise(const std::filesystem::path& output)
{
    deadline = Clock::now() + std::chrono::seconds(25);
    bool requested = false, observed = false, delivered = false, exited = false, modalSeen = false;
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
                std::vector<Node> nodes;
                walk(walker.Get(), modalRoot.Get(), 0, nodes);
                retainKeyboardFrame(nodes, "exact_owned_discard_dialog");
                snapshot(automation.Get(), output, L"tree-owned-discard-dialog");
                const Node* discard = nullptr;
                for (const auto& node : nodes) {
                    if (!exactDiscardNode(node)) continue;
                    if (discard) { ambiguous = true; break; }
                    discard = &node;
                }
                if (ambiguous) { reason = "blocked_ambiguous_discard_buttons"; break; }
                if (!discard) { reason = "blocked_exact_discard_button_unavailable"; Sleep(120); continue; }
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
        << ",\"discard_method\":\"" << method << "\",\"deadline_seconds\":25,\"save_requested\":false,\"actions\":[";
    for (size_t index = 0; index < actions.size(); ++index) { if (index) report << ','; report << actions[index]; }
    report << "],\"keyboard_frames\":[";
    for (size_t index = 0; index < keyboardFrames.size(); ++index) { if (index) report << ','; report << keyboardFrames[index]; }
    report << "]}\n";
    CloseHandle(targetProcess);
    return passed ? 0 : 2;
}
