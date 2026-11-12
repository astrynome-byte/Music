// SPDX-License-Identifier: GPL-3.0-only
// One private-note roundtrip in a disposable profile, only through actual UI.
struct NotesResult {
    bool dialogSelected = false, scoreAdded = false, panelObserved = false;
    bool compatibilityAcknowledged = false, annotationsEnabled = false;
    bool textObserved = false, saveRequested = false, savedControlObserved = false;
    bool savedChoiceObserved = false, restoredTextObserved = false, savedViewReady = false;
    std::string status = "blocked_notes_not_started";
};
static const std::wstring noteBack = L"Retour \u00e0 la biblioth\u00e8que";
static const std::wstring noteAck = L"J'ai compris la compatibilit\u00e9 du catalogue";
static const std::wstring noteEnable = L"Activer les notes priv\u00e9es";
static const std::wstring noteSelector = L"Choisir une note enregistr\u00e9e ou une nouvelle note";
static const std::wstring noteTextLabel = L"Texte de la note priv\u00e9e, 8 000 caract\u00e8res au maximum";

static bool noteReadText(IUIAutomation* automation, std::wstring& value)
{
    const Node node = focusedNode(automation);
    if (!collectionNodeIs(node, noteTextLabel, UIA_EditControlTypeId)) return false;
    // Preserve the TextPattern-first order proven in the actual collections UI.
    // A supported TextPattern that returns empty is not overridden by Value.
    ComPtr<IUIAutomationTextPattern> pattern;
    ComPtr<IUIAutomationTextRange> range;
    BSTR raw = nullptr;
    if (SUCCEEDED(node.element->GetCurrentPatternAs(UIA_TextPatternId, IID_PPV_ARGS(&pattern)))
        && pattern && SUCCEEDED(pattern->get_DocumentRange(&range)) && range) {
        if (SUCCEEDED(range->GetText(81, &raw))) { value = text(raw); return true; }
        SysFreeString(raw); raw = nullptr;
    }
    ComPtr<IUIAutomationValuePattern> fallback;
    if (SUCCEEDED(node.element->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&fallback))) && fallback) {
        if (SUCCEEDED(fallback->get_CurrentValue(&raw))) { value = text(raw); return true; }
        SysFreeString(raw);
    }
    return false;
}
static bool noteWaitFocus(IUIAutomation* automation, const std::filesystem::path& output,
                          const std::wstring& label, int type)
{
    const auto until = std::min(deadline, Clock::now() + std::chrono::seconds(5));
    while (collectionContext() && Clock::now() < until) {
        if (setExactCollectionFocus(automation, output, label, type)) return true;
        Sleep(160);
    }
    return false;
}
// After schema activation removes the focused button, Qt can expose only the
// main-window chrome through UIA. Re-enter the source-known Scores section and
// Notes panel using the same bounded discovery as the already-qualified Add
// focus restoration. Never invoke Back, the account menu, or any foreign node.
static bool noteRestoreSelectorFocus(IUIAutomation* automation, const std::filesystem::path& output)
{
    if (noteWaitFocus(automation, output, noteSelector, UIA_ComboBoxControlTypeId)) return true;
    bool search = false;
    for (int attempt = 0; attempt < 5 && collectionContext(); ++attempt) {
        const Node before = observeCollectionFocus(automation, "before_notes_section_reanchor_f6");
        if (before.pid != static_cast<int>(targetPid) || !before.enabled || before.offscreen) return false;
        const bool sent = sendNavigationKey(VK_F6, "reanchor_existing_notes_section_without_activation");
        Sleep(180);
        const Node after = observeCollectionFocus(automation, "after_notes_section_reanchor_f6");
        const auto label = controlLabel(after.name);
        if (!sent || after.pid != static_cast<int>(targetPid) || !after.enabled || after.offscreen) return false;
        search = after.type == UIA_EditControlTypeId
            && (label == L"Rechercher par titre, compositeur ou fichier"
                || label == L"Rechercher les partitions r\u00e9centes" || label == L"Search recent scores");
        if (search) break;
    }
    if (!search) return false;
    const Node field = focusedNode(automation);
    if (!collectionKey(automation, output, VK_TAB, controlLabel(field.name), UIA_EditControlTypeId,
            "reanchor_notes_via_selected_library_tab")) return false;
    const Node tab = observeCollectionFocus(automation, "notes_reanchor_selected_library_tab");
    const auto label = controlLabel(tab.name);
    if ((tab.type != UIA_TabItemControlTypeId && tab.type != UIA_RadioButtonControlTypeId)
        || (label != L"Biblioth\u00e8que locale" && label != L"Local library")) return false;
    return moveCollectionFocus(automation, output, VK_TAB, label, tab.type,
                noteBack, UIA_ButtonControlTypeId, "reanchor_notes_back_control_without_invoking")
        && moveCollectionFocus(automation, output, VK_DOWN, noteBack, UIA_ButtonControlTypeId,
                noteSelector, UIA_ComboBoxControlTypeId, "reanchor_private_note_selector_after_schema_activation");
}
static bool noteFocusText(IUIAutomation* automation, const std::filesystem::path& output)
{
    if (setExactCollectionFocus(automation, output, noteTextLabel, UIA_EditControlTypeId)) return true;
    if (!noteWaitFocus(automation, output, noteSelector, UIA_ComboBoxControlTypeId)) return false;
    const std::wstring measure = L"Rep\u00e8re manuel de mesure, z\u00e9ro pour aucun";
    // No modification to the numeric reference: Down only, from exact roles.
    return moveCollectionFocus(automation, output, VK_DOWN, noteSelector, UIA_ComboBoxControlTypeId,
                               measure, UIA_SpinnerControlTypeId, "observe_note_measure_without_editing")
        && collectionKey(automation, output, VK_ESCAPE, measure, UIA_SpinnerControlTypeId,
                         "finish_note_measure_edit_without_changing_value")
        && moveCollectionFocus(automation, output, VK_DOWN, measure, UIA_SpinnerControlTypeId,
                               noteTextLabel, UIA_EditControlTypeId, "focus_private_note_text");
}
static bool noteTextMatches(IUIAutomation* automation, const std::filesystem::path& output,
                            const std::wstring& expected)
{
    std::wstring actual;
    const bool match = noteFocusText(automation, output) && noteReadText(automation, actual) && actual == expected;
    actions.push_back("{\"action\":\"private_note_text_readback\",\"expected\":" + jsonQuoted(expected)
        + ",\"observed\":" + jsonQuoted(actual) + ",\"matched\":" + (match ? "true" : "false") + '}');
    return match;
}
static NotesResult exercisePrivateNote(IUIAutomation* automation, const std::filesystem::path& output,
                                      const std::wstring& fixtureRoot, const std::wstring& fixturePath,
                                      const std::wstring& expectedTitle, const std::wstring& noteText, bool restart)
{
    NotesResult result;
    const std::wstring add = L"Ajouter des partitions\u2026", open = L"Ouvrir " + expectedTitle;
    if (!restart) {
        if (!triggerVerifiedFocusedButton(automation, output, add, "open_add_only_controlled_score")) {
            result.status = "blocked_notes_add_control"; return result;
        }
        const auto selection = SelectOwnedScoreFile(automation, targetPid, targetProcess, mainWindow(), fixtureRoot,
            fixturePath, [&](const wchar_t* phase) { snapshot(automation, output, phase); });
        result.dialogSelected = selection.selected;
        actions.push_back("{\"action\":\"select_only_controlled_copy_for_notes\",\"selected\":"
            + std::string(selection.selected ? "true" : "false") + ",\"path\":" + jsonQuoted(fixturePath)
            + ",\"error\":" + std::to_string(selection.error) + ",\"diagnostic\":" + jsonQuoted(selection.diagnostic) + '}');
        if (!selection.selected || !restoreCollectionAddFocus(automation, output, true)) {
            result.status = "blocked_notes_controlled_add_dialog_or_restore"; return result;
        }
        // Observe the v1 collections button but deliberately do not activate it.
        if (!moveCollectionFocus(automation, output, VK_DOWN, add, UIA_ButtonControlTypeId,
                L"Activer les collections", UIA_ButtonControlTypeId, "observe_unactivated_collections_button")
            || !moveCollectionFocus(automation, output, VK_DOWN, L"Activer les collections", UIA_ButtonControlTypeId,
                open, UIA_ButtonControlTypeId, "observe_only_added_score_for_notes")) {
            result.status = "blocked_notes_added_score_control"; return result;
        }
        result.scoreAdded = true;
    } else {
        // Schema3 makes the ordinary collection filter visible, even when empty.
        if (!focusScoreOpenFromFilter(automation, output, L"Collection affich\u00e9e Toutes les partitions", expectedTitle)) {
            result.status = "blocked_notes_restart_score_control"; return result;
        }
    }
    const std::wstring favorite = L"Ajouter aux favoris " + expectedTitle;
    const std::wstring reveal = L"Afficher dans l'explorateur " + expectedTitle;
    const std::wstring notes = L"Notes priv\u00e9es de pratique " + expectedTitle;
    if (!moveCollectionFocus(automation, output, VK_RIGHT, open, UIA_ButtonControlTypeId, favorite, UIA_ButtonControlTypeId, "pass_favorite_without_activating")
        || !moveCollectionFocus(automation, output, VK_RIGHT, favorite, UIA_ButtonControlTypeId, reveal, UIA_ButtonControlTypeId, "pass_reveal_without_activating")
        || !moveCollectionFocus(automation, output, VK_RIGHT, reveal, UIA_ButtonControlTypeId, notes, UIA_ButtonControlTypeId, "focus_private_notes_for_controlled_score")
        || !triggerVerifiedFocusedButton(automation, output, notes, "open_controlled_score_private_notes")) {
        result.status = "blocked_notes_exact_entry_action"; return result;
    }
    result.panelObserved = noteWaitFocus(automation, output, noteBack, UIA_ButtonControlTypeId);
    if (!result.panelObserved) { result.status = "blocked_notes_inline_panel"; return result; }
    if (!restart) {
        if (!moveCollectionFocus(automation, output, VK_DOWN, noteBack, UIA_ButtonControlTypeId,
                noteAck, UIA_CheckBoxControlTypeId, "focus_private_notes_compatibility_checkbox")
            || !collectionKey(automation, output, VK_RETURN, noteAck, UIA_CheckBoxControlTypeId, "acknowledge_notes_schema3_disposable_profile_only")
            || !moveCollectionFocus(automation, output, VK_RIGHT, noteAck, UIA_CheckBoxControlTypeId,
                noteEnable, UIA_ButtonControlTypeId, "observe_enabled_private_notes_activation")) {
            result.status = "blocked_notes_compatibility_acknowledgement"; return result;
        }
        result.compatibilityAcknowledged = true; // Enabled activation is bound to the checked acknowledgement.
        if (!triggerVerifiedFocusedButton(automation, output, noteEnable, "activate_private_notes_in_fresh_qa_profile")) {
            result.status = "blocked_notes_activation_action"; return result;
        }
        result.annotationsEnabled = noteRestoreSelectorFocus(automation, output);
        if (!result.annotationsEnabled || !noteFocusText(automation, output)) {
            result.status = "blocked_notes_enabled_selector_or_text_control"; return result;
        }
        std::wstring initial;
        if (!noteReadText(automation, initial) || !initial.empty()
            || !collectionFocusIs(automation, noteTextLabel, UIA_EditControlTypeId)) {
            result.status = "blocked_notes_new_text_not_proven_empty"; return result;
        }
        const auto typed = SendOwnedAsciiIntoEmptyEdit(targetPid, targetProcess, mainWindow(), noteText);
        actions.push_back("{\"action\":\"owned_ascii_new_private_note\",\"text\":" + jsonQuoted(noteText)
            + ",\"sent\":" + (typed.sent ? "true" : "false") + ",\"input_count\":" + std::to_string(typed.inputCount)
            + ",\"error\":" + std::to_string(typed.error) + '}');
        if (!typed.sent) keyboardFailure = true;
        Sleep(200);
        result.textObserved = typed.sent && noteTextMatches(automation, output, noteText);
        // Escape ends TextInputArea editing; Enter would add a newline.
        if (!result.textObserved || !collectionKey(automation, output, VK_ESCAPE, noteTextLabel,
                UIA_EditControlTypeId, "finish_private_note_text_without_newline")) {
            result.status = "blocked_notes_typed_text_or_edit_finish"; return result;
        }
        if (!setExactCollectionFocus(automation, output, L"Enregistrer", UIA_ButtonControlTypeId)
            && !moveCollectionFocus(automation, output, VK_DOWN, noteTextLabel, UIA_EditControlTypeId,
                L"Enregistrer", UIA_ButtonControlTypeId, "focus_exact_private_note_save")) {
            result.status = "blocked_notes_save_control"; return result;
        }
        result.saveRequested = triggerVerifiedFocusedButton(automation, output, L"Enregistrer", "save_only_new_private_note");
        // Delete becomes enabled only for a committed selected note with no dirty draft.
        // Observe/focus it as corroboration, never invoke it.
        result.savedControlObserved = result.saveRequested
            && noteWaitFocus(automation, output, L"Supprimer la note", UIA_ButtonControlTypeId)
            && noteTextMatches(automation, output, noteText);
        if (!result.savedControlObserved) { result.status = "blocked_notes_saved_control_or_text"; return result; }
    } else {
        result.annotationsEnabled = noteWaitFocus(automation, output, noteSelector, UIA_ComboBoxControlTypeId);
        if (!result.annotationsEnabled || !collectionKey(automation, output, VK_RETURN, noteSelector,
                UIA_ComboBoxControlTypeId, "open_private_note_selection_on_restart")) {
            result.status = "blocked_notes_restart_selection"; return result;
        }
        bool chosen = false;
        for (int attempt = 0; attempt < 3 && collectionContext(); ++attempt) {
            const Node node = observeCollectionFocus(automation, "inspect_restart_private_note_choice");
            if (collectionNodeIs(node, noteText, UIA_ListItemControlTypeId)) {
                result.savedChoiceObserved = true;
                chosen = collectionKey(automation, output, VK_RETURN, noteText, UIA_ListItemControlTypeId, "select_exact_saved_private_note");
                break;
            }
            if (collectionNodeIs(node, L"Nouvelle note", UIA_ListItemControlTypeId)) {
                if (!collectionKey(automation, output, VK_DOWN, L"Nouvelle note", UIA_ListItemControlTypeId,
                        "navigate_only_to_saved_private_note")) break;
            } else break;
        }
        result.restoredTextObserved = chosen && noteTextMatches(automation, output, noteText);
        if (!result.restoredTextObserved) { result.status = "blocked_notes_restart_saved_text_readback"; return result; }
    }
    snapshot(automation, output, L"tree-private-note-observed");
    // Keep the verified saved text visible for the launcher's capture. The
    // exact saved/selected control proved no dirty draft; no musical file was
    // ever opened, so owned WM_CLOSE does not require a score-save dialog.
    result.savedViewReady = true;
    result.status = restart ? "private_note_restored_through_UIA_ready_for_close" : "private_note_saved_through_UIA_ready_for_close";
    return result;
}
