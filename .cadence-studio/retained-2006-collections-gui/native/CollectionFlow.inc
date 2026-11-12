// SPDX-License-Identifier: GPL-3.0-only
// Original controlled-copy collection UI probe. Included by UiaProbe.cpp.
struct AddResult {
    bool dialogSelected = false, scoreAdded = false, favoriteRequested = false, favoriteLabelObserved = false;
    bool collectionsEnabled = false, collectionCreated = false, collectionMember = false, collectionFilter = false;
    std::string status = "blocked_add_not_started";
};
struct ExistingScoreResult {
    bool favoriteRestored = false, collectionRestored = false, collectionFilter = false;
    bool openRequested = false, editorTitleObserved = false;
    std::wstring observedTitle;
    std::string status = "blocked_existing_score_not_started";
};

static bool collectionContext()
{
    const HWND main = mainWindow();
    return Clock::now() < deadline && alive() && owned(main) && IsWindowVisible(main) && IsWindowEnabled(main) && !keyboardFailure;
}
static Node observeCollectionFocus(IUIAutomation* automation, const char* phase)
{
    Node node = focusedNode(automation);
    actions.push_back("{\"action\":\"observe_collection_focus\",\"phase\":\"" + std::string(phase)
        + "\",\"name\":" + jsonQuoted(node.name) + ",\"control_label\":" + jsonQuoted(controlLabel(node.name))
        + ",\"pid\":" + std::to_string(node.pid) + ",\"control_type\":" + std::to_string(node.type)
        + ",\"enabled\":" + (node.enabled ? "true" : "false") + ",\"offscreen\":" + (node.offscreen ? "true" : "false") + '}');
    return node;
}
static bool collectionNodeIs(const Node& node, const std::wstring& label, int type)
{
    return collectionContext() && node.pid == static_cast<int>(targetPid) && node.enabled && !node.offscreen
        && node.type == type && controlLabel(node.name) == label;
}
static bool collectionFocusIs(IUIAutomation* automation, const std::wstring& label, int type)
{
    return collectionNodeIs(observeCollectionFocus(automation, "verify_focus"), label, type);
}
static bool collectionKey(IUIAutomation* automation, const std::filesystem::path& output,
                          WORD key, const std::wstring& from, int fromType, const char* purpose)
{
    if (!collectionFocusIs(automation, from, fromType)) return false;
    auto nodes = snapshot(automation, output, L"tree-collection-before-key");
    retainKeyboardFrame(nodes, std::string("before_") + purpose);
    if (!collectionFocusIs(automation, from, fromType)) return false;
    const bool sent = sendNavigationKey(key, purpose);
    Sleep(180);
    nodes = snapshot(automation, output, L"tree-collection-after-key");
    retainKeyboardFrame(nodes, std::string("after_") + purpose);
    const Node after = observeCollectionFocus(automation, purpose);
    return sent && collectionContext() && after.pid == static_cast<int>(targetPid);
}
static bool moveCollectionFocus(IUIAutomation* automation, const std::filesystem::path& output,
                                WORD key, const std::wstring& from, int fromType,
                                const std::wstring& to, int toType, const char* purpose)
{
    return collectionKey(automation, output, key, from, fromType, purpose) && collectionFocusIs(automation, to, toType);
}

// First prefer the exact unique exposed accessible control; Qt may expose only
// its active child, in which case use bounded source-known semantic transitions.
static bool setExactCollectionFocus(IUIAutomation* automation, const std::filesystem::path& output,
                                    const std::wstring& label, int type)
{
    if (collectionFocusIs(automation, label, type)) return true;
    const auto nodes = snapshot(automation, output, L"tree-collection-focus-discovery");
    const Node* match = nullptr;
    for (const Node& node : nodes) {
        if (!collectionNodeIs(node, label, type)) continue;
        if (match) return false;
        match = &node;
    }
    if (!match) return false;
    int pid = 0;
    if (!collectionContext() || FAILED(match->element->get_CurrentProcessId(&pid)) || pid != static_cast<int>(targetPid)) return false;
    const HRESULT hr = match->element->SetFocus();
    actions.push_back("{\"action\":\"set_unique_collection_focus\",\"label\":" + jsonQuoted(label)
        + ",\"pid\":" + std::to_string(pid) + ",\"hresult\":" + std::to_string(static_cast<long>(hr)) + '}');
    Sleep(120);
    return SUCCEEDED(hr) && collectionFocusIs(automation, label, type);
}

static bool restoreCollectionAddFocus(IUIAutomation* automation, const std::filesystem::path& output, bool nativeDialogJustClosed = false)
{
    const std::wstring add = L"Ajouter des partitions\u2026";
    if (!nativeDialogJustClosed && setExactCollectionFocus(automation, output, add, UIA_ButtonControlTypeId)) return true;
    // F6 is the inherited bounded section-discovery operation. Every resulting
    // child is checked; never send a following Tab from an unrelated focus.
    bool search = false;
    for (int attempt = 0; attempt < 5 && collectionContext(); ++attempt) {
        const Node before = observeCollectionFocus(automation, "before_restore_f6");
        if (before.pid != 0 && before.pid != static_cast<int>(targetPid)) return false;
        const bool sent = sendNavigationKey(VK_F6, "restore_library_section_semantically");
        Sleep(180);
        const Node node = observeCollectionFocus(automation, "after_restore_f6");
        const auto label = controlLabel(node.name);
        if (!sent || node.pid != static_cast<int>(targetPid) || !node.enabled || node.offscreen) return false;
        search = node.type == UIA_EditControlTypeId && (label == L"Rechercher par titre, compositeur ou fichier"
            || label == L"Rechercher les partitions r\u00e9centes" || label == L"Search recent scores");
        if (search) break;
    }
    if (!search) return false;
    const Node field = focusedNode(automation);
    if (!collectionKey(automation, output, VK_TAB, controlLabel(field.name), UIA_EditControlTypeId, "restore_selected_library_tab")) return false;
    const Node tab = observeCollectionFocus(automation, "restored_library_tab");
    const auto label = controlLabel(tab.name);
    if ((tab.type != UIA_TabItemControlTypeId && tab.type != UIA_RadioButtonControlTypeId)
        || (label != L"Biblioth\u00e8que locale" && label != L"Local library")) return false;
    return moveCollectionFocus(automation, output, VK_TAB, label, tab.type, add, UIA_ButtonControlTypeId, "restore_add_panel");
}

static bool focusCollectionRow(IUIAutomation* automation, const std::filesystem::path& output,
                               const std::wstring& filter)
{
    if (setExactCollectionFocus(automation, output, filter, UIA_ComboBoxControlTypeId)) return true;
    if (!restoreCollectionAddFocus(automation, output)) return false;
    return moveCollectionFocus(automation, output, VK_DOWN, L"Ajouter des partitions\u2026", UIA_ButtonControlTypeId,
                               filter, UIA_ComboBoxControlTypeId, "focus_collection_filter_row");
}

// Only the two actual choices of this clean QA catalogue are accepted. Unlike
// coordinates or index-only selection, every popup item label is observed.
static bool chooseCollection(IUIAutomation* automation, const std::filesystem::path& output,
                             const std::wstring& comboLabel, const std::wstring& wanted,
                             const std::wstring& collectionName, bool classification)
{
    if (!collectionFocusIs(automation, comboLabel, UIA_ComboBoxControlTypeId)) return false;
    if (!collectionKey(automation, output, VK_RETURN, comboLabel, UIA_ComboBoxControlTypeId, "open_exact_collection_dropdown")) return false;
    for (int attempt = 0; attempt < 4 && collectionContext(); ++attempt) {
        const Node node = observeCollectionFocus(automation, "inspect_collection_dropdown_item");
        const auto label = controlLabel(node.name);
        if (collectionNodeIs(node, wanted, UIA_ListItemControlTypeId)) {
            if (!collectionKey(automation, output, VK_RETURN, wanted, UIA_ListItemControlTypeId, "choose_exact_collection_item")) return false;
            Sleep(300);
            return true;
        }
        if (!classification && collectionNodeIs(node, L"Toutes les partitions", UIA_ListItemControlTypeId) && wanted == collectionName) {
            if (!collectionKey(automation, output, VK_DOWN, label, node.type, "navigate_to_controlled_collection_item")) return false;
        } else if (!classification && collectionNodeIs(node, collectionName, UIA_ListItemControlTypeId) && wanted == L"Toutes les partitions") {
            if (!collectionKey(automation, output, VK_UP, label, node.type, "navigate_to_all_scores_item")) return false;
        } else if (classification && collectionNodeIs(node, comboLabel, UIA_ComboBoxControlTypeId)) {
            // Classification has currentIndex=-1. Its popup may leave the
            // originating combo active until the first navigation Down.
            if (!collectionKey(automation, output, VK_DOWN, comboLabel, node.type, "focus_first_classification_item")) return false;
        } else return false;
    }
    return false;
}

static bool readFocusedEditText(IUIAutomation* automation, std::wstring& value)
{
    const Node node = focusedNode(automation);
    if (!collectionNodeIs(node, L"Nom de collection", UIA_EditControlTypeId)) return false;
    ComPtr<IUIAutomationValuePattern> pattern;
    if (SUCCEEDED(node.element->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&pattern)))) {
        BSTR raw = nullptr;
        if (SUCCEEDED(pattern->get_CurrentValue(&raw))) { value = text(raw); return true; }
    }
    ComPtr<IUIAutomationTextPattern> textPattern;
    ComPtr<IUIAutomationTextRange> range;
    BSTR raw = nullptr;
    if (FAILED(node.element->GetCurrentPatternAs(UIA_TextPatternId, IID_PPV_ARGS(&textPattern)))
        || FAILED(textPattern->get_DocumentRange(&range)) || !range || FAILED(range->GetText(81, &raw))) return false;
    value = text(raw);
    return true;
}

static bool fillNewCollectionName(IUIAutomation* automation, const std::filesystem::path& output,
                                  const std::wstring& collectionName)
{
    std::wstring before;
    if (!collectionFocusIs(automation, L"Nom de collection", UIA_EditControlTypeId)
        || !readFocusedEditText(automation, before) || !before.empty()) return false;
    const Node edit = focusedNode(automation);
    ComPtr<IUIAutomationValuePattern> valuePattern;
    HRESULT setResult = E_NOINTERFACE;
    if (SUCCEEDED(edit.element->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&valuePattern)))) {
        BOOL readOnly = TRUE;
        if (SUCCEEDED(valuePattern->get_CurrentIsReadOnly(&readOnly)) && !readOnly
            && collectionFocusIs(automation, L"Nom de collection", UIA_EditControlTypeId)) {
            BSTR value = SysAllocStringLen(collectionName.data(), static_cast<UINT>(collectionName.size()));
            if (!value) return false;
            setResult = valuePattern->SetValue(value);
            SysFreeString(value);
        }
    }
    std::wstring after;
    bool written = SUCCEEDED(setResult) && readFocusedEditText(automation, after) && after == collectionName;
    // AccessibleItemInterface.setText is an upstream stub. If SetValue did not
    // change the still-empty exact field, type bounded ASCII with fresh PID,
    // foreground and Win32 focus checks. Never replace existing or unknown text.
    if (!written && collectionFocusIs(automation, L"Nom de collection", UIA_EditControlTypeId)
        && readFocusedEditText(automation, before) && before.empty()) {
        const OwnedKeyResult sent = SendOwnedAsciiIntoEmptyEdit(targetPid, targetProcess, mainWindow(), collectionName);
        actions.push_back("{\"action\":\"owned_ascii_collection_name\",\"text\":" + jsonQuoted(collectionName)
            + ",\"pid\":" + std::to_string(targetPid) + ",\"sent\":" + (sent.sent ? "true" : "false")
            + ",\"input_count\":" + std::to_string(sent.inputCount) + ",\"error\":" + std::to_string(sent.error) + '}');
        if (!sent.sent) keyboardFailure = true;
        Sleep(180);
        written = sent.sent && readFocusedEditText(automation, after) && after == collectionName;
    }
    actions.push_back("{\"action\":\"verify_collection_name_field\",\"value_pattern_set_hresult\":"
        + std::to_string(static_cast<long>(setResult)) + ",\"expected\":" + jsonQuoted(collectionName)
        + ",\"observed\":" + jsonQuoted(after) + ",\"matched\":" + (written ? "true" : "false") + '}');
    snapshot(automation, output, L"tree-collection-name-filled");
    if (!written) return false;
    // Release the real QML TextInput's LeftRight shortcut override before Right
    // can move to Create. Return here accepts the text; it does not create.
    return collectionKey(automation, output, VK_RETURN, L"Nom de collection", UIA_EditControlTypeId, "accept_collection_name_edit");
}

static bool focusScoreOpenFromFilter(IUIAutomation* automation, const std::filesystem::path& output,
                                     const std::wstring& filter, const std::wstring& expectedTitle)
{
    if (!focusCollectionRow(automation, output, filter)) return false;
    return moveCollectionFocus(automation, output, VK_DOWN, filter, UIA_ComboBoxControlTypeId,
                               L"Ouvrir " + expectedTitle, UIA_ButtonControlTypeId, "focus_controlled_score_from_filter");
}

static AddResult exerciseAddAndFavorite(IUIAutomation* automation, const std::filesystem::path& output,
                                        const std::wstring& fixtureRoot, const std::wstring& fixturePath,
                                        const std::wstring& expectedTitle, const std::wstring& collectionName)
{
    AddResult result;
    const std::wstring add = L"Ajouter des partitions\u2026", all = L"Collection affich\u00e9e Toutes les partitions";
    const std::wstring selected = L"Collection affich\u00e9e " + collectionName;
    const std::wstring open = L"Ouvrir " + expectedTitle, favorite = L"Retirer des favoris " + expectedTitle;
    if (!triggerVerifiedFocusedButton(automation, output, add, "open_add_scores_dialog")) {
        result.status = "blocked_focused_add_button_unavailable"; return result;
    }
    const auto selection = SelectOwnedScoreFile(automation, targetPid, targetProcess, mainWindow(), fixtureRoot,
                                                fixturePath, [&](const wchar_t* phase) { snapshot(automation, output, phase); });
    result.dialogSelected = selection.selected;
    actions.push_back("{\"action\":\"select_controlled_copy_in_owned_native_dialog\",\"path\":" + jsonQuoted(fixturePath)
        + ",\"selected\":" + (selection.selected ? "true" : "false") + ",\"error\":" + std::to_string(selection.error)
        + ",\"diagnostic\":" + jsonQuoted(selection.diagnostic) + '}');
    if (!selection.selected) { result.status = "blocked_native_add_dialog"; return result; }
    Sleep(300);
    if (!restoreCollectionAddFocus(automation, output, true)) { result.status = "blocked_add_focus_restore"; return result; }
    // A clean v1 catalogue offers Enable; assert this label before activating.
    if (!moveCollectionFocus(automation, output, VK_DOWN, add, UIA_ButtonControlTypeId,
                             L"Activer les collections", UIA_ButtonControlTypeId, "observe_enable_collections")) {
        result.status = "blocked_enable_collections_control"; return result;
    }
    if (!triggerVerifiedFocusedButton(automation, output, L"Activer les collections", "enable_collections")) {
        result.status = "blocked_enable_collections_action"; return result;
    }
    Sleep(350);
    result.collectionsEnabled = focusCollectionRow(automation, output, all);
    if (!result.collectionsEnabled) { result.status = "blocked_enabled_collection_filter_unobserved"; return result; }
    if (!moveCollectionFocus(automation, output, VK_DOWN, all, UIA_ComboBoxControlTypeId, open, UIA_ButtonControlTypeId, "observe_added_score")) {
        result.status = "blocked_added_score_control"; return result;
    }
    result.scoreAdded = true;
    if (!moveCollectionFocus(automation, output, VK_RIGHT, open, UIA_ButtonControlTypeId,
                             L"Ajouter aux favoris " + expectedTitle, UIA_ButtonControlTypeId, "focus_favorite")) {
        result.status = "blocked_favorite_focus"; return result;
    }
    result.favoriteRequested = triggerVerifiedFocusedButton(automation, output, L"Ajouter aux favoris " + expectedTitle, "favorite_added_score");
    Sleep(250);
    // Model reset may invalidate the old active node: reacquire from Add/filter.
    if (!result.favoriteRequested || !focusScoreOpenFromFilter(automation, output, all, expectedTitle)
        || !moveCollectionFocus(automation, output, VK_RIGHT, open, UIA_ButtonControlTypeId, favorite, UIA_ButtonControlTypeId, "observe_favorite_set")) {
        result.status = "blocked_favorite_remove_label"; return result;
    }
    result.favoriteLabelObserved = true;
    if (!focusCollectionRow(automation, output, all)
        || !moveCollectionFocus(automation, output, VK_RIGHT, all, UIA_ComboBoxControlTypeId,
                                L"Nom de collection", UIA_EditControlTypeId, "focus_collection_name")) {
        result.status = "blocked_collection_name_field"; return result;
    }
    if (!fillNewCollectionName(automation, output, collectionName)) { result.status = "blocked_collection_name_set_or_readback"; return result; }
    if (!setExactCollectionFocus(automation, output, L"Cr\u00e9er", UIA_ButtonControlTypeId)
        && !moveCollectionFocus(automation, output, VK_RIGHT, L"Nom de collection", UIA_EditControlTypeId,
                                L"Cr\u00e9er", UIA_ButtonControlTypeId, "focus_create_collection")) {
        result.status = "blocked_create_collection_control"; return result;
    }
    if (!triggerVerifiedFocusedButton(automation, output, L"Cr\u00e9er", "create_controlled_collection")) {
        result.status = "blocked_create_collection_action"; return result;
    }
    Sleep(350);
    result.collectionCreated = focusCollectionRow(automation, output, selected);
    if (!result.collectionCreated) { result.status = "blocked_created_collection_filter"; return result; }
    // Creation selects the empty collection. Return to All before membership.
    if (!chooseCollection(automation, output, selected, L"Toutes les partitions", collectionName, false)
        || !focusScoreOpenFromFilter(automation, output, all, expectedTitle)
        || !moveCollectionFocus(automation, output, VK_DOWN, open, UIA_ButtonControlTypeId,
                                L"Ajouter " + expectedTitle + L" \u00e0 une collection", UIA_ComboBoxControlTypeId, "focus_score_classification")) {
        result.status = "blocked_classification_control"; return result;
    }
    if (!chooseCollection(automation, output, L"Ajouter " + expectedTitle + L" \u00e0 une collection", collectionName, collectionName, true)) {
        result.status = "blocked_classification_dropdown"; return result;
    }
    if (!focusCollectionRow(automation, output, all)
        || !chooseCollection(automation, output, all, collectionName, collectionName, false)
        || !focusScoreOpenFromFilter(automation, output, selected, expectedTitle)) {
        result.status = "blocked_classified_score_in_collection_filter"; return result;
    }
    result.collectionFilter = true;
    const auto classify = L"Ajouter " + expectedTitle + L" \u00e0 une collection";
    const auto remove = L"Retirer de cette collection " + expectedTitle;
    if (!moveCollectionFocus(automation, output, VK_DOWN, open, UIA_ButtonControlTypeId, classify, UIA_ComboBoxControlTypeId, "observe_collection_member_row")
        || !moveCollectionFocus(automation, output, VK_RIGHT, classify, UIA_ComboBoxControlTypeId, remove, UIA_ButtonControlTypeId, "observe_collection_remove_member_control")) {
        result.status = "blocked_member_remove_control_unobserved"; return result;
    }
    result.collectionMember = true;
    snapshot(automation, output, L"tree-collection-added");
    result.status = "controlled_score_added_favorited_and_collection_member_observed";
    return result;
}

static ExistingScoreResult VerifyFavoriteAndOpen(IUIAutomation* automation, const std::filesystem::path& output,
                                                const std::wstring& expectedTitle, const std::wstring& fixturePath,
                                                const std::wstring& collectionName)
{
    ExistingScoreResult result;
    const std::wstring all = L"Collection affich\u00e9e Toutes les partitions";
    const std::wstring selected = L"Collection affich\u00e9e " + collectionName;
    const std::wstring open = L"Ouvrir " + expectedTitle, favorite = L"Retirer des favoris " + expectedTitle;
    const auto stem = std::filesystem::path(fixturePath).stem().wstring();
    if (!focusScoreOpenFromFilter(automation, output, all, expectedTitle)
        || !moveCollectionFocus(automation, output, VK_RIGHT, open, UIA_ButtonControlTypeId, favorite, UIA_ButtonControlTypeId, "observe_restored_favorite")) {
        result.status = "blocked_restored_favorite_control"; return result;
    }
    result.favoriteRestored = true;
    if (!focusCollectionRow(automation, output, all)
        || !chooseCollection(automation, output, all, collectionName, collectionName, false)
        || !focusScoreOpenFromFilter(automation, output, selected, expectedTitle)) {
        result.status = "blocked_restored_collection_or_member"; return result;
    }
    result.collectionFilter = true;
    const auto classify = L"Ajouter " + expectedTitle + L" \u00e0 une collection";
    const auto remove = L"Retirer de cette collection " + expectedTitle;
    if (!moveCollectionFocus(automation, output, VK_DOWN, open, UIA_ButtonControlTypeId, classify, UIA_ComboBoxControlTypeId, "inspect_restored_collection_membership")
        || !moveCollectionFocus(automation, output, VK_RIGHT, classify, UIA_ComboBoxControlTypeId, remove, UIA_ButtonControlTypeId, "observe_restored_remove_membership_control")) {
        result.status = "blocked_restored_member_control"; return result;
    }
    result.collectionRestored = true;
    if (!focusScoreOpenFromFilter(automation, output, selected, expectedTitle)) { result.status = "blocked_restored_open_focus"; return result; }
    result.openRequested = triggerVerifiedFocusedButton(automation, output, open, "open_restored_collection_score");
    if (!result.openRequested) { result.status = "blocked_existing_score_open"; return result; }
    const auto until = std::min(deadline, Clock::now() + std::chrono::seconds(10));
    while (Clock::now() < until && alive()) {
        const auto main = mainWindow();
        result.observedTitle = windowTitle(main);
        result.editorTitleObserved = collectionContext() && !stem.empty()
            && (result.observedTitle.find(stem) != std::wstring::npos || result.observedTitle.find(expectedTitle) != std::wstring::npos);
        if (result.editorTitleObserved) break;
        Sleep(150);
    }
    snapshot(automation, output, L"tree-score-opened");
    result.status = result.editorTitleObserved ? "restored_favorite_collection_and_real_editor_caption_observed" : "blocked_editor_caption_unobserved";
    return result;
}
