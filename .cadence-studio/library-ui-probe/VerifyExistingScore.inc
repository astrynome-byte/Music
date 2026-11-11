// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
// Included after UiaProbe's owned navigation helpers and before wmain.
struct ExistingScoreResult {
    bool favoriteRestored = false;
    bool openRequested = false;
    bool editorTitleObserved = false;
    std::wstring observedTitle;
    std::string status = "blocked_existing_score_not_started";
};

static ExistingScoreResult VerifyFavoriteAndOpen(IUIAutomation* automation,
                                               const std::filesystem::path& output,
                                               const std::wstring& expectedTitle,
                                               const std::wstring& fixturePath)
{
    ExistingScoreResult result;
    const std::wstring stem = std::filesystem::path(fixturePath).stem().wstring();
    auto contextValid = [&]() {
        const HWND main = mainWindow();
        return automation && Clock::now() < deadline && alive() && owned(main)
               && IsWindowVisible(main) && IsWindowEnabled(main);
    };
    if (expectedTitle.empty() || stem.empty() || !contextValid()) {
        result.status = "blocked_existing_score_arguments_or_owned_context"; return result;
    }
    auto observeFocus = [&](const char* phase) {
        const Node node = focusedNode(automation);
        actions.push_back("{\"action\":\"observe_restarted_library_focus\",\"phase\":\"" + std::string(phase)
                          + "\",\"name\":" + jsonQuoted(node.name) + ",\"control_label\":" + jsonQuoted(controlLabel(node.name))
                          + ",\"pid\":" + std::to_string(node.pid) + ",\"control_type\":" + std::to_string(node.type)
                          + ",\"enabled\":" + (node.enabled ? "true" : "false") + ",\"offscreen\":" + (node.offscreen ? "true" : "false") + '}');
        return node;
    };
    auto isButton = [&](const Node& node, const std::wstring& label) {
        return contextValid() && node.pid == static_cast<int>(targetPid) && node.type == UIA_ButtonControlTypeId
               && node.enabled && !node.offscreen && controlLabel(node.name) == label;
    };
    auto navigate = [&](WORD key, const std::wstring& from, const std::wstring& to,
                        const char* purpose, const wchar_t* before, const wchar_t* after) {
        if (!isButton(observeFocus(purpose), from)) return false;
        auto nodes = snapshot(automation, output, before);
        retainKeyboardFrame(nodes, std::string("before_") + purpose);
        if (!isButton(observeFocus("immediately_before_existing_score_key"), from)) return false;
        const bool sent = sendNavigationKey(key, purpose);
        Sleep(250);
        nodes = snapshot(automation, output, after);
        retainKeyboardFrame(nodes, std::string("after_") + purpose);
        const Node current = observeFocus("after_existing_score_key");
        return sent && isButton(current, to);
    };
    const std::wstring open = L"Ouvrir " + expectedTitle;
    const std::wstring favorite = L"Retirer des favoris " + expectedTitle;
    if (!navigate(VK_DOWN, L"Ajouter des partitions\u2026", open, "restart_focus_existing_score_open",
                  L"tree-restart-before-down", L"tree-restart-after-down")) {
        result.status = "blocked_existing_score_open_control"; return result;
    }
    if (!navigate(VK_RIGHT, open, favorite, "restart_observe_restored_favorite",
                  L"tree-restart-before-right", L"tree-restart-after-right")) {
        result.status = "blocked_restored_favorite_control"; return result;
    }
    result.favoriteRestored = true;
    // Only inspect the restored favorite. Never activate its toggle.
    if (!navigate(VK_LEFT, favorite, open, "restart_return_focus_to_existing_score_open",
                  L"tree-restart-before-left", L"tree-restart-after-left")) {
        result.status = "blocked_return_to_existing_score_open_control"; return result;
    }
    if (!isButton(observeFocus("before_verified_existing_score_open"), open)) {
        result.status = "blocked_existing_score_open_focus_changed"; return result;
    }
    result.openRequested = triggerVerifiedFocusedButton(automation, output, open, "open_restored_library_score");
    observeFocus("after_existing_score_open_return");
    if (!result.openRequested) { result.status = "blocked_existing_score_open_return"; return result; }

    const auto captionDeadline = std::min(deadline, Clock::now() + std::chrono::seconds(8));
    unsigned polls = 0;
    while (Clock::now() < captionDeadline && alive()) {
        ++polls;
        const HWND main = mainWindow();
        result.observedTitle = windowTitle(main);
        const bool matches = owned(main) && IsWindowVisible(main) && IsWindowEnabled(main)
                             && (result.observedTitle.find(expectedTitle) != std::wstring::npos
                                 || result.observedTitle.find(stem) != std::wstring::npos);
        if (matches) {
            snapshot(automation, output, L"tree-score-opened");
            const HWND current = mainWindow();
            result.observedTitle = windowTitle(current);
            result.editorTitleObserved = contextValid() && (result.observedTitle.find(expectedTitle) != std::wstring::npos
                                                           || result.observedTitle.find(stem) != std::wstring::npos);
            if (result.editorTitleObserved) break;
        }
        const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(captionDeadline - Clock::now()).count();
        if (remaining > 0) Sleep(static_cast<DWORD>(remaining < 100 ? remaining : 100));
    }
    actions.push_back("{\"action\":\"observe_editor_caption_after_library_open\",\"pid\":" + std::to_string(targetPid)
                      + ",\"title\":" + jsonQuoted(result.observedTitle) + ",\"expected_title\":" + jsonQuoted(expectedTitle)
                      + ",\"fixture_stem\":" + jsonQuoted(stem) + ",\"poll_count\":" + std::to_string(polls)
                      + ",\"observed\":" + (result.editorTitleObserved ? "true" : "false")
                      + ",\"musical_content_or_editing_validated\":false}");
    result.status = result.editorTitleObserved ? "restored_favorite_observed_and_editor_caption_after_open"
                                              : "blocked_existing_score_editor_caption_unobserved";
    return result;
}
