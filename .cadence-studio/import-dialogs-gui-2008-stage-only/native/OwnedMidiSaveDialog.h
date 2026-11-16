// SPDX-License-Identifier: GPL-3.0-only
// Private QA candidate. Requires real Windows compilation and GUI validation.
#pragma once
#include "OwnedWaveFileDialog.h"
#include "OwnedKeyboard.h"
#include <set>
#include <vector>

struct OwnedMidiSaveResult {
    bool saved = false, valueSet = false, valueVerified = false, invokeRequested = false;
    bool saveDialogClosed = false, MIDIFileObserved = false, transcriptionDialogHidden = false;
    HWND dialog = nullptr;
    HRESULT result = E_FAIL;
    std::wstring path, diagnostic;
    // Saving and queued file-open are different postconditions. This helper
    // NEVER claims that a score was displayed or imported successfully.
};

namespace cadence_owned_midi_save_detail {
using namespace cadence_owned_file_dialog_detail;
using Identity = std::vector<int>;
using FocusProof = std::function<bool(HWND, const wchar_t*)>;

inline Identity identity(IUIAutomationElement* element)
{
    SAFEARRAY* array = nullptr;
    const HRESULT fetched = element ? element->GetRuntimeId(&array) : E_POINTER;
    struct Cleanup { SAFEARRAY* value; ~Cleanup() { if (value) SafeArrayDestroy(value); } } cleanup {array};
    VARTYPE kind = VT_EMPTY; LONG first = 0, last = -1;
    if (fetched != S_OK || !array || SafeArrayGetDim(array) != 1
        || SafeArrayGetElemsize(array) != sizeof(int) || SafeArrayGetVartype(array, &kind) != S_OK
        || kind != VT_I4 || SafeArrayGetLBound(array, 1, &first) != S_OK
        || SafeArrayGetUBound(array, 1, &last) != S_OK || last < first
        || static_cast<long long>(last) - first + 1 > 16) return {};
    Identity result;
    for (LONG index = first; ; ++index) {
        int value = 0;
        if (SafeArrayGetElement(array, &index, &value) != S_OK) return {};
        result.push_back(value); if (index == last) break;
    }
    return result;
}

inline bool saveDialog(HWND window, HWND owner, DWORD pid)
{
    if (window == owner || !ownedChain(window, owner, pid)
        || !IsWindowVisible(window) || !IsWindowEnabled(window)) return false;
    wchar_t name[64] {}, title[256] {};
    return GetClassNameW(window, name, 64) && GetWindowTextW(window, title, 256)
        && std::wstring(name) == L"#32770"
        && std::wstring(title) == L"Enregistrer un nouveau MIDI puis l'ouvrir dans l'éditeur";
}
struct Search { HWND owner; DWORD pid; ULONGLONG until; HWND match = nullptr; unsigned count = 0; };
inline BOOL CALLBACK inspectSave(HWND window, LPARAM data)
{
    auto& search = *reinterpret_cast<Search*>(data);
    if (GetTickCount64() >= search.until) return FALSE;
    if (saveDialog(window, search.owner, search.pid)) { search.match = window; ++search.count; }
    return search.count < 2;
}
inline bool belongsToDialog(IUIAutomation* a, IUIAutomationElement* element,
                            HWND window, DWORD pid, ULONGLONG until)
{
    ComPtr<IUIAutomationTreeWalker> walker;
    if (!a || a->get_RawViewWalker(&walker) != S_OK || !walker) return false;
    ComPtr<IUIAutomationElement> current = element;
    std::set<Identity> seen;
    for (unsigned depth = 0; current && depth < 18 && GetTickCount64() < until; ++depth) {
        int actualPid = 0; UIA_HWND handle {};
        if (current->get_CurrentProcessId(&actualPid) != S_OK || actualPid != static_cast<int>(pid)) return false;
        const auto id = identity(current.Get());
        if (id.empty() || !seen.insert(id).second || current->get_CurrentNativeWindowHandle(&handle) != S_OK) return false;
        if (reinterpret_cast<HWND>(handle) == window) return owned(window, pid);
        if (handle && !owned(reinterpret_cast<HWND>(handle), pid)) return false;
        ComPtr<IUIAutomationElement> parent;
        if (walker->GetParentElement(current.Get(), &parent) != S_OK) return false;
        current = parent;
    }
    return false;
}
inline bool uniqueSaveButton(IUIAutomation* a, HWND dialog, DWORD pid,
                              ComPtr<IUIAutomationElement>& match, ULONGLONG until)
{
    ComPtr<IUIAutomationElement> root;
    if (a->ElementFromHandle(dialog, &root) != S_OK || !root || GetTickCount64() >= until) return false;
    VARIANT value; VariantInit(&value); value.vt = VT_I4; value.lVal = UIA_ButtonControlTypeId;
    ComPtr<IUIAutomationCondition> condition;
    if (a->CreatePropertyCondition(UIA_ControlTypePropertyId, value, &condition) != S_OK) return false;
    ComPtr<IUIAutomationElementArray> rows;
    if (root->FindAll(TreeScope_Descendants, condition.Get(), &rows) != S_OK || !rows) return false;
    int count = 0; unsigned matches = 0;
    if (rows->get_Length(&count) != S_OK || count < 0 || count > 256) return false;
    for (int index = 0; index < count && GetTickCount64() < until; ++index) {
        ComPtr<IUIAutomationElement> row;
        if (rows->GetElement(index, &row) != S_OK || !row) return false;
        int actualPid = 0, type = 0; BOOL enabled = FALSE, offscreen = TRUE;
        if (row->get_CurrentProcessId(&actualPid) != S_OK) return false;
        if (actualPid != static_cast<int>(pid)) continue; // Never use foreign controls.
        if (row->get_CurrentControlType(&type) != S_OK || row->get_CurrentIsEnabled(&enabled) != S_OK
            || row->get_CurrentIsOffscreen(&offscreen) != S_OK) return false;
        BSTR rawName = nullptr, rawId = nullptr;
        const HRESULT named = row->get_CurrentName(&rawName); auto name = takeString(rawName);
        const HRESULT identified = row->get_CurrentAutomationId(&rawId); auto id = takeString(rawId);
        if (named != S_OK || identified != S_OK) return false;
        if (type != UIA_ButtonControlTypeId || !enabled || offscreen || id != L"1"
            || (name != L"Save" && name != L"Enregistrer")) continue;
        if (++matches > 1 || !belongsToDialog(a, row.Get(), dialog, pid, until)) return false;
        match = row;
    }
    return matches == 1 && GetTickCount64() < until;
}
inline bool missing(const std::wstring& path)
{
    SetLastError(ERROR_SUCCESS);
    const DWORD value = GetFileAttributesW(path.c_str()), error = GetLastError();
    return value == INVALID_FILE_ATTRIBUTES && error == ERROR_FILE_NOT_FOUND;
}
inline bool focusedFilename(IUIAutomation* a, IUIAutomationElement* edit, HWND dialog,
                             DWORD pid, ULONGLONG until, const FocusProof& proof, const wchar_t* phase)
{
    if (GetTickCount64() >= until || !proof(dialog, phase)) return false;
    OwnedKeyResult native;
    if (!cadence_owned_keyboard_detail::sampleOwnedFocus(pid, native)
        || !cadence_owned_keyboard_detail::nativeContext(dialog, pid, native)) return false;
    ComPtr<IUIAutomationElement> focused; BOOL same = FALSE, hasFocus = FALSE;
    if (a->GetFocusedElement(&focused) != S_OK || !focused
        || a->CompareElements(focused.Get(), edit, &same) != S_OK || !same
        || focused->get_CurrentHasKeyboardFocus(&hasFocus) != S_OK || !hasFocus) return false;
    const auto expected = identity(edit), current = identity(focused.Get());
    OwnedKeyResult after;
    return !expected.empty() && expected == current && belongsToDialog(a, edit, dialog, pid, until)
        && cadence_owned_keyboard_detail::sampleOwnedFocus(pid, after)
        && after.foreground == native.foreground && after.focus == native.focus
        && cadence_owned_keyboard_detail::nativeContext(dialog, pid, after) && GetTickCount64() < until;
}
} // namespace cadence_owned_midi_save_detail

// Saves ONLY a new exact-name derivative under the already controlled fixture
// directory. Application source additionally uses QIODevice::NewOnly atomically.
// No input is sent after Invoke, and no old-dialog focus is required afterwards.
inline OwnedMidiSaveResult SaveOwnedMidiDraft(
    IUIAutomation* automation, DWORD pid, HANDLE process, HWND transcriptionDialog,
    const std::wstring& fixtureRoot, const std::wstring& outputPath,
    unsigned maximumMilliseconds,
    const cadence_owned_midi_save_detail::FocusProof& proof,
    const std::function<void(const wchar_t*)>& diagnostic)
{
    using namespace cadence_owned_midi_save_detail;
    OwnedMidiSaveResult result;
    const ULONGLONG until = GetTickCount64() + std::min<unsigned>(maximumMilliseconds, 20000);
    auto stop = [&](const wchar_t* message, HRESULT hr = E_ACCESSDENIED) {
        result.diagnostic = message; result.result = hr; return result;
    };
    if (!maximumMilliseconds || !automation || !proof || !diagnostic || !alive(pid, process) || !owned(transcriptionDialog, pid))
        return stop(L"Missing owned live process, UIA or proof callbacks.");
    std::wstring root, path;
    if (!fullLocalPath(fixtureRoot, root) || !fullLocalPath(outputPath, path)
        || !noReparseComponents(root, until)) return stop(L"Controlled existing local root required.");
    while (!root.empty() && root.back() == L'\\') root.pop_back();
    const std::wstring expected = root + L"\\Cadence-QA-three-notes-transcription.mid";
    if (!sameText(path, expected) || !missing(path)) return stop(L"Exact new MIDI derivative required; existing targets refused.");
    ReadHandle rootHandle;
    rootHandle.value = CreateFileW(root.c_str(), FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    BY_HANDLE_FILE_INFORMATION rootInfo {};
    if (rootHandle.value == INVALID_HANDLE_VALUE || !GetFileInformationByHandle(rootHandle.value, &rootInfo)
        || !(rootInfo.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
        || (rootInfo.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) return stop(L"Controlled directory handle unavailable.");
    std::wstring originalRoot;
    if (!finalPath(rootHandle.value, originalRoot)) return stop(L"Controlled directory identity unavailable.");
    auto rootUnchanged = [&]() {
        std::wstring now;
        return GetTickCount64() < until && noReparseComponents(root, until)
            && finalPath(rootHandle.value, now) && sameText(now, originalRoot);
    };
    while (GetTickCount64() < until && alive(pid, process)) {
        Search search {transcriptionDialog, pid, until};
        EnumWindows(inspectSave, reinterpret_cast<LPARAM>(&search));
        if (search.count > 1) return stop(L"Ambiguous Save dialogs refused.");
        if (search.count == 1) { result.dialog = search.match; break; }
        waitBriefly(until);
    }
    auto context = [&]() { return rootUnchanged() && alive(pid, process)
        && saveDialog(result.dialog, transcriptionDialog, pid); };
    if (!result.dialog || !context()) return stop(L"Exact owned MIDI Save dialog unavailable.");
    ComPtr<IUIAutomationElement> edit;
    std::wstring name, id;
    if (uniqueControl(automation, result.dialog, pid, true, edit, name, id, until) != S_OK
        || !edit || !focusedFilename(automation, edit.Get(), result.dialog, pid, until, proof, L"before-MIDI-filename-value"))
        return stop(L"Exact focused filename control and ancestry not proved.");
    ComPtr<IUIAutomationValuePattern> value;
    BOOL readOnly = TRUE;
    if (edit->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&value)) != S_OK || !value
        || value->get_CurrentIsReadOnly(&readOnly) != S_OK || readOnly) return stop(L"Writable filename value unavailable.");
    try { diagnostic(L"midi-save-before-value"); } catch (...) { return stop(L"Diagnostic callback blocked."); }
    if (!context() || !missing(path)
        || !focusedFilename(automation, edit.Get(), result.dialog, pid, until, proof, L"immediately-before-MIDI-filename-value"))
        return stop(L"Save context, filename focus or fresh target changed.");
    if (value->SetValue(path.c_str()) != S_OK) return stop(L"Setting exact derivative path failed.");
    result.valueSet = true;
    BSTR raw = nullptr;
    const HRESULT readValue = value->get_CurrentValue(&raw); auto actualPath = takeString(raw);
    result.valueVerified = readValue == S_OK && sameText(actualPath, path);
    if (!result.valueVerified) return stop(L"Exact derivative path not retained.");
    ComPtr<IUIAutomationElement> save;
    if (!uniqueSaveButton(automation, result.dialog, pid, save, until)) return stop(L"Exact owned ID1 Save button unavailable.");
    ComPtr<IUIAutomationInvokePattern> invoke;
    if (save->GetCurrentPatternAs(UIA_InvokePatternId, IID_PPV_ARGS(&invoke)) != S_OK || !invoke)
        return stop(L"Save InvokePattern unavailable.");
    const auto saveIdentity = identity(save.Get());
    try { diagnostic(L"midi-save-before-invoke"); } catch (...) { return stop(L"Diagnostic callback blocked."); }
    raw = nullptr; const HRESULT reread = value->get_CurrentValue(&raw); actualPath = takeString(raw);
    ComPtr<IUIAutomationElement> saveAgain;
    BOOL same = FALSE;
    if (!context() || !missing(path) || reread != S_OK || !sameText(actualPath, path)
        || saveIdentity.empty() || !uniqueSaveButton(automation, result.dialog, pid, saveAgain, until)
        || automation->CompareElements(save.Get(), saveAgain.Get(), &same) != S_OK || !same
        || identity(saveAgain.Get()) != saveIdentity
        || !focusedFilename(automation, edit.Get(), result.dialog, pid, until, proof, L"immediately-before-MIDI-save-invoke"))
        return stop(L"Save control, focus or fresh target changed before Invoke.");
    // The callback and preceding UIA queries can yield. Re-read the actual
    // filename AFTER them, then perform only native checks before Invoke.
    OwnedKeyResult beforeFinalRead, afterFinalRead;
    if (!cadence_owned_keyboard_detail::sampleOwnedFocus(pid, beforeFinalRead)
        || !cadence_owned_keyboard_detail::nativeContext(result.dialog, pid, beforeFinalRead))
        return stop(L"Native Save context changed before final filename read.");
    raw = nullptr; const HRESULT finalRead = value->get_CurrentValue(&raw); actualPath = takeString(raw);
    if (finalRead != S_OK || !sameText(actualPath, path) || !context() || !missing(path)
        || !alive(pid, process) || !cadence_owned_keyboard_detail::sampleOwnedFocus(pid, afterFinalRead)
        || afterFinalRead.foreground != beforeFinalRead.foreground || afterFinalRead.focus != beforeFinalRead.focus
        || !cadence_owned_keyboard_detail::nativeContext(result.dialog, pid, afterFinalRead)
        || GetForegroundWindow() != afterFinalRead.foreground || GetTickCount64() >= until)
        return stop(L"Exact filename, fresh target or native context changed before Invoke.");
    result.invokeRequested = true;
    result.result = invoke->Invoke();
    if (result.result != S_OK) return stop(L"Save Invoke failed.", result.result);
    try { diagnostic(L"midi-save-after-invoke-no-old-focus-required"); }
    catch (...) { return stop(L"Post-Invoke diagnostic callback blocked."); }
    while (GetTickCount64() < until && alive(pid, process) && rootUnchanged()) {
        result.saveDialogClosed = !IsWindow(result.dialog) || !IsWindowVisible(result.dialog);
        result.transcriptionDialogHidden = !IsWindow(transcriptionDialog) || !IsWindowVisible(transcriptionDialog);
        if (result.saveDialogClosed && result.transcriptionDialogHidden) {
            ReadHandle file;
            file.value = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
            BY_HANDLE_FILE_INFORMATION info {}; unsigned char magic[14] {}; DWORD count = 0;
            if (file.value != INVALID_HANDLE_VALUE && GetFileInformationByHandle(file.value, &info)
                && !(info.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))
                && GetFileType(file.value) == FILE_TYPE_DISK && info.nFileSizeHigh == 0
                && info.nFileSizeLow >= sizeof(magic) && info.nFileSizeLow <= 1024 * 1024
                && ReadFile(file.value, magic, sizeof(magic), &count, nullptr) && count == sizeof(magic)
                && magic[0] == 'M' && magic[1] == 'T' && magic[2] == 'h' && magic[3] == 'd') {
                std::wstring finalFile;
                if (!finalPath(file.value, finalFile)
                    || !sameText(finalFile, originalRoot + L"\\Cadence-QA-three-notes-transcription.mid"))
                    return stop(L"Saved MIDI resolved outside the controlled directory.");
                result.MIDIFileObserved = true; result.saved = true; result.path = path; result.result = S_OK;
                result.diagnostic = L"New MIDI derivative observed; Save and transcription dialogs hidden. Actual notation opening remains a separate proof.";
                return result;
            }
        }
        waitBriefly(until);
    }
    return stop(L"New MIDI file and closed dialogs not observed within the deadline.", HRESULT_FROM_WIN32(ERROR_TIMEOUT));
}
