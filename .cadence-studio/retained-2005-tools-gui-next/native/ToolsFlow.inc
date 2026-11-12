// SPDX-License-Identifier: GPL-3.0-only
// Real UI-only probes of retained Cadence pages. No bank/file injection.
struct ToolsResult {
    bool soundsNavigation = false, soundsPage = false, generalOffer = false, generalSize = false;
    bool generalLicenseControl = false, generalLicenseText = false;
    bool lessonsNavigation = false, lessonsTab = false, lessonOpen = false, editorTitle = false;
    unsigned lessonCount = 0;
    std::wstring editorCaption, captionBeforeOpen, editorWindowClass, licenseExcerpt;
    std::string soundsStatus = "blocked_sounds_not_started", lessonsStatus = "blocked_lessons_not_started";
};
static const std::wstring generalDownload = L"T\u00e9l\u00e9charger 30.8 Mio \u00b7 GeneralUser GS";
static const std::wstring generalInstruments = L"Voir les instruments (287) \u00b7 GeneralUser GS";
static const std::wstring generalLicense = L"Lire la licence compl\u00e8te \u00b7 GeneralUser GS";
static const std::wstring fullLicense = L"Licence compl\u00e8te de GeneralUser GS, GeneralUser GS License v2.0 (texte int\u00e9gral ci-dessous)";
static const std::vector<std::wstring> lessonTitles {
    L"Garder la pulsation", L"Lire les dur\u00e9es et les silences", L"Donner une direction \u00e0 la phrase",
    L"Construire et entendre des accords", L"Suivre deux voix ind\u00e9pendantes", L"Chanter une petite phrase",
    L"Relier port\u00e9e et tablature", L"Superposer un rythme de batterie"
};
static std::wstring lessonButton(unsigned index) { return L"Ouvrir l\u2019exercice : " + lessonTitles.at(index); }
static bool toolsContext()
{
    const auto main = mainWindow();
    return alive() && Clock::now() < deadline && owned(main) && IsWindowVisible(main)
        && IsWindowEnabled(main) && !keyboardFailure;
}
static bool toolsLabel(const Node& node, const std::wstring& label)
{
    const bool buttonExpected = label == generalDownload || label == generalInstruments || label == generalLicense
        || label == L"Actualiser" || label == L"Ouvrir le dossier \u00b7 MS Basic"
        || label.rfind(L"Ouvrir l\u2019exercice : ", 0) == 0;
    return toolsContext() && node.element && node.pid == static_cast<int>(targetPid)
        && node.enabled && !node.offscreen && controlLabel(node.name) == label
        && (!buttonExpected || node.type == UIA_ButtonControlTypeId);
}
static Node toolsFocus(IUIAutomation* automation, const char* purpose)
{
    Node node = focusedNode(automation);
    actions.push_back("{\"action\":\"observe_tools_focus\",\"purpose\":\"" + std::string(purpose)
        + "\",\"name\":" + jsonQuoted(node.name) + ",\"label\":" + jsonQuoted(controlLabel(node.name))
        + ",\"pid\":" + std::to_string(node.pid) + ",\"type\":" + std::to_string(node.type) + '}');
    return node;
}
static const Node* uniqueTool(const std::vector<Node>& nodes, const std::wstring& label)
{
    const Node* result = nullptr;
    for (const auto& node : nodes) {
        if (!toolsLabel(node, label)) continue;
        if (result) return nullptr;
        result = &node;
    }
    return result;
}
static bool focusTool(IUIAutomation* automation, const Node* node, const std::wstring& label)
{
    if (!node || !toolsLabel(*node, label)) return false;
    int pid = 0;
    if (FAILED(node->element->get_CurrentProcessId(&pid)) || pid != static_cast<int>(targetPid)) return false;
    const HRESULT result = node->element->SetFocus();
    Sleep(120);
    Node focused = toolsFocus(automation, "after_exact_set_focus");
    BOOL same = FALSE;
    const HRESULT compared = focused.element ? automation->CompareElements(node->element.Get(), focused.element.Get(), &same) : E_POINTER;
    return SUCCEEDED(result) && SUCCEEDED(compared) && same && toolsLabel(focused, label);
}
static bool toolsKey(IUIAutomation* automation, const std::filesystem::path& output,
                     WORD key, const std::wstring& from, const char* purpose)
{
    const Node before = toolsFocus(automation, "before_semantic_key");
    if (!toolsLabel(before, from) || (key == VK_RETURN && !interactiveType(before.type))) return false;
    const auto nodes = snapshot(automation, output, L"tree-tools-before-key");
    retainKeyboardFrame(nodes, std::string("before_") + purpose);
    if (!toolsLabel(toolsFocus(automation, "recheck_semantic_key"), from)) return false;
    const bool sent = sendNavigationKey(key, purpose);
    Sleep(200);
    const Node after = toolsFocus(automation, purpose);
    return sent && toolsContext() && after.pid == static_cast<int>(targetPid);
}
static bool toolsF6(IUIAutomation* automation, const char* purpose)
{
    const Node before = toolsFocus(automation, "before_owned_section_discovery");
    if (!toolsContext() || (before.pid != 0 && before.pid != static_cast<int>(targetPid))) return false;
    const bool sent = sendNavigationKey(VK_F6, purpose);
    Sleep(200);
    const Node after = toolsFocus(automation, purpose);
    return sent && toolsContext() && after.pid == static_cast<int>(targetPid);
}
static bool activateToolPage(IUIAutomation* automation, const std::filesystem::path& output,
                             const std::wstring& wanted)
{
    const auto until = std::min(deadline, Clock::now() + std::chrono::seconds(18));
    for (unsigned attempt = 0; attempt < 12 && toolsContext() && Clock::now() < until; ++attempt) {
        auto nodes = snapshot(automation, output, L"tree-tools-navigation");
        if (const auto node = uniqueTool(nodes, wanted)) {
            if (interactiveType(node->type) && invokeSemantic(node, "activate_exact_tools_page")) { Sleep(350); return true; }
            if (focusTool(automation, node, wanted) && toolsKey(automation, output, VK_RETURN, wanted, "activate_focused_tools_page")) return true;
        }
        const Node focus = toolsFocus(automation, "inspect_tools_menu");
        const auto label = controlLabel(focus.name);
        const bool menuRole = focus.type == UIA_RadioButtonControlTypeId || focus.type == UIA_TabItemControlTypeId;
        if (menuRole && toolsLabel(focus, wanted)) return toolsKey(automation, output, VK_RETURN, wanted, "activate_observed_tools_menu");
        if (menuRole && toolsLabel(focus, L"Apprendre") && wanted == L"Collections sonores") {
            if (!toolsKey(automation, output, VK_UP, L"Apprendre", "previous_source_defined_home_menu_item")) return false;
        } else if (menuRole && (toolsLabel(focus, L"Partitions") || toolsLabel(focus, L"Plugins")
                        || toolsLabel(focus, L"Collections sonores"))) {
            if (!toolsKey(automation, output, VK_DOWN, label, "next_source_defined_home_menu_item")) return false;
        } else if (!toolsF6(automation, "discover_owned_home_menu_section")) return false;
    }
    return false;
}
static bool focusGeneralLicense(IUIAutomation* automation, const std::filesystem::path& output, ToolsResult& result)
{
    for (unsigned attempt = 0; attempt < 10 && toolsContext(); ++attempt) {
        auto nodes = snapshot(automation, output, L"tree-generaluser-offer");
        const Node focus = toolsFocus(automation, "inspect_generaluser_offer");
        const bool download = uniqueTool(nodes, generalDownload) || toolsLabel(focus, generalDownload);
        result.generalOffer = result.generalOffer || download;
        result.generalSize = result.generalSize || download;
        result.soundsPage = result.soundsPage || download || uniqueTool(nodes, L"Actualiser");
        if (result.generalOffer) {
            if (const auto license = uniqueTool(nodes, generalLicense)) {
                if (focusTool(automation, license, generalLicense)) { result.generalLicenseControl = true; return true; }
            }
        }
        if (toolsLabel(focus, generalLicense)) { result.generalLicenseControl = true; return true; }
        if (toolsLabel(focus, L"Actualiser") || toolsLabel(focus, L"Ouvrir le dossier \u00b7 MS Basic")) {
            if (!toolsKey(automation, output, VK_TAB, controlLabel(focus.name), "next_observed_sound_collection_panel")) return false;
        } else if (toolsLabel(focus, generalDownload)) {
            if (!toolsKey(automation, output, VK_DOWN, generalDownload, "navigate_without_activating_download")) return false;
        } else if (toolsLabel(focus, generalInstruments)) {
            if (!toolsKey(automation, output, VK_RIGHT, generalInstruments, "navigate_to_license_without_install")) return false;
        } else if (!toolsF6(automation, "discover_generaluser_card")) return false;
    }
    return false;
}
static bool readGeneralLicense(IUIAutomation* automation, std::wstring& content)
{
    const Node node = toolsFocus(automation, "inspect_readonly_license");
    if (!toolsLabel(node, fullLicense)) return false;
    BSTR value = nullptr;
    ComPtr<IUIAutomationValuePattern> pattern;
    HRESULT got = E_NOINTERFACE;
    if (SUCCEEDED(node.element->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&pattern)))) {
        // Read only. Qt may omit the UIA readOnly flag even though the source
        // TextInputArea is readOnly; this client never invokes SetValue here.
        got = pattern->get_CurrentValue(&value);
    }
    if (SUCCEEDED(got) && value) content.assign(value, std::min<UINT>(SysStringLen(value), 8192));
    SysFreeString(value); value = nullptr;
    if (content.find(L"GeneralUser GS v2.0.3") == std::wstring::npos) {
        ComPtr<IUIAutomationTextPattern> textPattern;
        ComPtr<IUIAutomationTextRange> range;
        if (FAILED(node.element->GetCurrentPatternAs(UIA_TextPatternId, IID_PPV_ARGS(&textPattern)))
            || FAILED(textPattern->get_DocumentRange(&range)) || !range) return false;
        got = range->GetText(8192, &value);
        if (SUCCEEDED(got) && value) content.assign(value, std::min<UINT>(SysStringLen(value), 8192));
        SysFreeString(value); value = nullptr;
    }
    return SUCCEEDED(got) && content.find(L"GeneralUser GS v2.0.3") != std::wstring::npos
        && content.find(L"License v2.0") != std::wstring::npos
        && content.find(L"License of the complete work") != std::wstring::npos;
}
static void probeSounds(IUIAutomation* automation, const std::filesystem::path& output, ToolsResult& result)
{
    result.soundsNavigation = activateToolPage(automation, output, L"Collections sonores");
    if (!result.soundsNavigation) { result.soundsStatus = "blocked_sounds_navigation"; return; }
    if (!focusGeneralLicense(automation, output, result)) { result.soundsStatus = "blocked_generaluser_offer_or_license_control"; return; }
    if (!toolsKey(automation, output, VK_RETURN, generalLicense, "open_only_generaluser_license")) {
        result.soundsStatus = "blocked_generaluser_license_action"; return;
    }
    Sleep(250);
    result.generalLicenseText = readGeneralLicense(automation, result.licenseExcerpt);
    snapshot(automation, output, L"tree-generaluser-license");
    result.soundsStatus = result.generalOffer && result.generalSize && result.generalLicenseControl && result.generalLicenseText
        ? "generaluser_offer_size_and_actual_license_text_observed_without_install"
        : "blocked_generaluser_identity_size_or_actual_license_text";
}
static bool focusFirstLesson(IUIAutomation* automation, const std::filesystem::path& output, ToolsResult& result)
{
    for (unsigned attempt = 0; attempt < 10 && toolsContext(); ++attempt) {
        auto nodes = snapshot(automation, output, L"tree-local-lessons");
        result.lessonsTab = result.lessonsTab || uniqueTool(nodes, L"Parcours hors ligne");
        if (const auto node = uniqueTool(nodes, lessonButton(0))) if (focusTool(automation, node, lessonButton(0))) return true;
        const Node focus = toolsFocus(automation, "inspect_local_lessons_panel");
        result.lessonsTab = result.lessonsTab || toolsLabel(focus, L"Parcours hors ligne");
        if (toolsLabel(focus, lessonButton(0))) return true;
        if (focus.type == UIA_EditControlTypeId && (toolsLabel(focus, L"Rechercher") || toolsLabel(focus, L"Search"))) {
            if (!toolsKey(automation, output, VK_TAB, controlLabel(focus.name), "enter_selected_learn_tab_panel")) return false;
        } else if (toolsLabel(focus, L"Parcours hors ligne")) {
            if (!toolsKey(automation, output, VK_TAB, L"Parcours hors ligne", "enter_selected_offline_lessons_panel")) return false;
        } else if (!toolsF6(automation, "discover_embedded_offline_lessons_panel")) return false;
    }
    return false;
}
static void probeLessons(IUIAutomation* automation, const std::filesystem::path& output, ToolsResult& result)
{
    result.lessonsNavigation = activateToolPage(automation, output, L"Apprendre");
    if (!result.lessonsNavigation) { result.lessonsStatus = "blocked_learn_navigation"; return; }
    if (!focusFirstLesson(automation, output, result)) { result.lessonsStatus = "blocked_first_offline_exercise_control"; return; }
    result.lessonCount = 1;
    for (unsigned index = 1; index < lessonTitles.size(); ++index) {
        if (!toolsKey(automation, output, VK_DOWN, lessonButton(index - 1), "inspect_next_original_lesson")
            || !toolsLabel(toolsFocus(automation, "verify_next_original_lesson"), lessonButton(index))) break;
        ++result.lessonCount;
    }
    if (result.lessonCount != lessonTitles.size()) { result.lessonsStatus = "blocked_all_eight_lesson_controls_not_observed"; return; }
    for (unsigned index = result.lessonCount - 1; index > 0; --index) {
        if (!toolsKey(automation, output, VK_UP, lessonButton(index), "return_to_first_original_lesson")
            || !toolsLabel(toolsFocus(automation, "verify_previous_original_lesson"), lessonButton(index - 1))) {
            result.lessonsStatus = "blocked_return_to_first_lesson"; return;
        }
    }
    // This is the final mutating UI action. The real application creates its own
    // UUID exercise copy; the wrapper must corroborate its new bytes after close.
    result.captionBeforeOpen = windowTitle(mainWindow());
    result.lessonOpen = toolsKey(automation, output, VK_RETURN, lessonButton(0), "open_embedded_exercise_as_user_copy");
    const auto until = std::min(deadline, Clock::now() + std::chrono::seconds(12));
    while (result.lessonOpen && toolsContext() && Clock::now() < until) {
        result.editorCaption = windowTitle(mainWindow());
        wchar_t className[256] = {};
        GetClassNameW(mainWindow(), className, 256);
        result.editorWindowClass = className;
        // The complete editor uses the imported score's name; depending on the
        // existing reader this is its filename stem or its embedded work title.
        result.editorTitle = result.editorCaption != result.captionBeforeOpen
            && result.editorWindowClass.rfind(L"Qt", 0) == 0
            && (result.editorCaption.find(lessonTitles.front()) != std::wstring::npos
                || result.editorCaption.find(L"pulsation") != std::wstring::npos);
        if (result.editorTitle) break;
        Sleep(200);
    }
    snapshot(automation, output, L"tree-offline-exercise-editor");
    result.lessonsStatus = result.editorTitle ? "eight_original_lessons_and_real_copied_exercise_editor_caption_observed"
        : "blocked_original_exercise_editor_caption";
}

int wmain(int argc, wchar_t** argv)
{
    std::filesystem::path output;
    bool closeExercise = false;
    if ((argc - 1) % 2) return 1;
    for (int index = 1; index + 1 < argc; index += 2) {
        if (std::wstring(argv[index]) == L"--pid") targetPid = wcstoul(argv[index + 1], nullptr, 10);
        else if (std::wstring(argv[index]) == L"--output") output = argv[index + 1];
        else if (std::wstring(argv[index]) == L"--close-exercise") {
            if (closeExercise || std::wstring(argv[index + 1]) != L"true") return 1;
            closeExercise = true;
        }
        else return 1;
    }
    if (!targetPid || !std::filesystem::is_directory(output) || std::filesystem::exists(output / L"uia-report.json")
        || std::filesystem::exists(output / L"close-report.json")) return 1;
    targetProcess = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, targetPid);
    if (!alive()) { if (targetProcess) CloseHandle(targetProcess); return 1; }
    if (closeExercise) return closeOwnedExercise(output);
    deadline = Clock::now() + std::chrono::seconds(140);
    ToolsResult result;
    HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED), activated = initialized;
    if (SUCCEEDED(initialized)) {
        ComPtr<IUIAutomation> automation;
        activated = CoCreateInstance(__uuidof(CUIAutomation8), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        if (FAILED(activated)) activated = CoCreateInstance(__uuidof(CUIAutomation), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
        ComPtr<IUIAutomation2> bounded;
        if (SUCCEEDED(activated) && SUCCEEDED(automation.As(&bounded))
            && SUCCEEDED(bounded->put_ConnectionTimeout(800)) && SUCCEEDED(bounded->put_TransactionTimeout(1000))) {
            const auto readyUntil = std::min(deadline, Clock::now() + std::chrono::seconds(25));
            while (alive() && Clock::now() < readyUntil) {
                if (closeIntroductionOnly() || closeOwnedWelcomeOnly()) Sleep(250);
                auto nodes = snapshot(automation.Get(), output, L"tree-tools-ready");
                const Node* home = find(nodes, { L"Accueil", L"Home" });
                if (home) { invokeSemantic(home, "activate_owned_home_before_tools"); Sleep(250); break; }
                if (uniqueTool(nodes, L"Collections sonores") || uniqueTool(nodes, L"Apprendre")) break;
                Sleep(250);
            }
            const auto overallDeadline = deadline;
            deadline = std::min(overallDeadline, Clock::now() + std::chrono::seconds(45));
            probeSounds(automation.Get(), output, result);
            deadline = overallDeadline;
            // A blocked optional bank page must not prevent the independent course.
            if (toolsContext()) probeLessons(automation.Get(), output, result);
        }
        bounded.Reset(); automation.Reset(); CoUninitialize();
    }
    const bool passed = result.soundsNavigation && result.soundsPage && result.generalOffer && result.generalSize
        && result.generalLicenseControl && result.generalLicenseText && result.lessonsNavigation && result.lessonsTab
        && result.lessonCount == 8 && result.lessonOpen && result.editorTitle;
    std::ofstream report(output / L"uia-report.json", std::ios::binary);
    report << "{\"schema_version\":1,\"pid\":" << targetPid << ",\"status\":\"" << (passed ? "passed_ui_controls_only" : "blocked")
        << "\",\"sounds_status\":\"" << result.soundsStatus << "\",\"lessons_status\":\"" << result.lessonsStatus
        << "\",\"com_activation_hresult\":" << static_cast<long>(activated);
    auto flag = [&](const char* key, bool value) { report << ",\"" << key << "\":" << (value ? "true" : "false"); };
    flag("sounds_navigation_delivered", result.soundsNavigation); flag("sounds_page_control_observed", result.soundsPage);
    flag("generaluser_offer_control_observed", result.generalOffer); flag("generaluser_download_size_control_observed", result.generalSize);
    flag("generaluser_license_control_observed", result.generalLicenseControl); flag("generaluser_license_text_observed", result.generalLicenseText);
    flag("lessons_navigation_delivered", result.lessonsNavigation); flag("offline_lessons_tab_observed", result.lessonsTab);
    report << ",\"offline_lesson_count_observed\":" << result.lessonCount;
    flag("lesson_open_requested", result.lessonOpen); flag("lesson_editor_title_observed", result.editorTitle);
    report << ",\"lesson_editor_title\":" << jsonQuoted(result.editorCaption)
        << ",\"window_caption_before_exercise_open\":" << jsonQuoted(result.captionBeforeOpen)
        << ",\"lesson_editor_window_class\":" << jsonQuoted(result.editorWindowClass)
        << ",\"generaluser_license_excerpt\":" << jsonQuoted(result.licenseExcerpt.substr(0, 4096));
    flag("bank_download_or_install_requested", false); flag("account_or_purchase_action_requested", false);
    flag("coach_tested", false); flag("musical_editing_tested", false); flag("audio_playback_tested", false);
    flag("copy_files_verified_by_native_client", false);
    report << ",\"global_deadline_seconds\":140,\"sounds_phase_deadline_seconds\":45,\"keyboard_gesture_attempts\":" << keyboardGestureAttempts
        << ",\"keyboard_failure_stops_sequence\":" << (keyboardFailure ? "true" : "false") << ",\"actions\":[";
    for (size_t index = 0; index < actions.size(); ++index) { if (index) report << ','; report << actions[index]; }
    report << "],\"keyboard_frames\":[";
    for (size_t index = 0; index < keyboardFrames.size(); ++index) { if (index) report << ','; report << keyboardFrames[index]; }
    report << "]}\n";
    CloseHandle(targetProcess);
    return passed ? 0 : 2;
}
