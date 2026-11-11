// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <windows.h>
#include <UIAutomation.h>
#include <wrl/client.h>
#include <algorithm>
#include <functional>
#include <string>

struct OwnedFileSelectionResult {
    bool selected = false;
    bool valueSet = false;
    bool valueVerified = false;
    bool invokeRequested = false;
    bool dialogClosed = false;
    bool mainEnabled = false;
    HWND dialog = nullptr;
    DWORD error = 0;
    HRESULT result = E_FAIL;
    HRESULT editDiscovery = E_PENDING;
    HRESULT valuePattern = E_PENDING;
    HRESULT readOnlyState = E_PENDING;
    HRESULT setValue = E_PENDING;
    HRESULT readValue = E_PENDING;
    HRESULT buttonDiscovery = E_PENDING;
    HRESULT invokePattern = E_PENDING;
    HRESULT invoke = E_PENDING;
    std::wstring editName;
    std::wstring editAutomationId;
    std::wstring buttonName;
    std::wstring buttonAutomationId;
    std::wstring verifiedPath;
    std::wstring diagnostic;
};

namespace cadence_owned_file_dialog_detail {
using Microsoft::WRL::ComPtr;

inline void waitBriefly(ULONGLONG deadline)
{
    const ULONGLONG now = GetTickCount64();
    if (now < deadline) {
        const ULONGLONG remaining = deadline - now;
        Sleep(static_cast<DWORD>(remaining < 50 ? remaining : 50));
    }
}

struct ReadHandle {
    HANDLE value = INVALID_HANDLE_VALUE;
    ~ReadHandle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    ReadHandle() = default;
    ReadHandle(const ReadHandle&) = delete;
    ReadHandle& operator=(const ReadHandle&) = delete;
};

inline bool sameText(const std::wstring& left, const std::wstring& right)
{
    return left.size() == right.size()
           && CompareStringOrdinal(left.data(), static_cast<int>(left.size()),
                                   right.data(), static_cast<int>(right.size()), TRUE) == CSTR_EQUAL;
}

inline OwnedFileSelectionResult fail(OwnedFileSelectionResult result, const wchar_t* diagnostic,
                                     HRESULT hr = E_FAIL, DWORD error = 0)
{
    result.selected = false;
    result.result = hr;
    result.error = error;
    result.diagnostic = diagnostic;
    return result;
}

inline bool alive(DWORD expectedPid, HANDLE process)
{
    DWORD code = 0;
    return expectedPid && process && process != INVALID_HANDLE_VALUE && GetProcessId(process) == expectedPid
           && GetExitCodeProcess(process, &code) && code == STILL_ACTIVE
           && WaitForSingleObject(process, 0) == WAIT_TIMEOUT;
}

inline bool owned(HWND window, DWORD expectedPid)
{
    DWORD pid = 0;
    return window && GetWindowThreadProcessId(window, &pid) && pid == expectedPid;
}

inline bool ownedChain(HWND dialog, HWND main, DWORD expectedPid)
{
    HWND current = dialog;
    for (unsigned hops = 0; current && hops <= 8; ++hops) {
        if (!owned(current, expectedPid)) return false;
        if (current == main) return true;
        current = GetWindow(current, GW_OWNER);
    }
    return false;
}

inline bool isDialog(HWND dialog, HWND main, DWORD expectedPid)
{
    if (dialog == main || !ownedChain(dialog, main, expectedPid)
        || !IsWindowVisible(dialog) || !IsWindowEnabled(dialog)) return false;
    wchar_t className[64] {}, title[256] {};
    if (!GetClassNameW(dialog, className, 64) || !GetWindowTextW(dialog, title, 256)) return false;
    return std::wstring(className) == L"#32770"
           && std::wstring(title) == L"Ajouter des partitions \u00e0 la biblioth\u00e8que";
}

struct DialogSearch {
    HWND main = nullptr;
    DWORD pid = 0;
    ULONGLONG deadline = 0;
    HWND match = nullptr;
    unsigned count = 0;
};

inline BOOL CALLBACK inspectDialog(HWND window, LPARAM parameter)
{
    auto& search = *reinterpret_cast<DialogSearch*>(parameter);
    if (GetTickCount64() >= search.deadline) return FALSE;
    if (isDialog(window, search.main, search.pid)) {
        search.match = window;
        ++search.count;
    }
    return search.count < 2;
}

inline bool fullLocalPath(const std::wstring& input, std::wstring& output)
{
    // Fixtures belong to a new local runner-temp directory, never UNC/device
    // paths or drive-relative paths that could access an unintended location.
    if (input.size() < 3 || input.size() > 32767 || input.find(L'\0') != std::wstring::npos
        || !((input[0] >= L'A' && input[0] <= L'Z') || (input[0] >= L'a' && input[0] <= L'z'))
        || input[1] != L':' || (input[2] != L'\\' && input[2] != L'/')) return false;
    const DWORD needed = GetFullPathNameW(input.c_str(), 0, nullptr, nullptr);
    if (!needed || needed > 32768) return false;
    output.assign(needed, L'\0');
    const DWORD count = GetFullPathNameW(input.c_str(), needed, output.data(), nullptr);
    if (!count || count >= needed) return false;
    output.resize(count);
    std::replace(output.begin(), output.end(), L'/', L'\\');
    return true;
}

inline bool noReparseComponents(const std::wstring& path, ULONGLONG deadline)
{
    size_t position = 2;
    while ((position = path.find(L'\\', position + 1)) != std::wstring::npos) {
        if (GetTickCount64() >= deadline) return false;
        const DWORD attributes = GetFileAttributesW(path.substr(0, position).c_str());
        if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return false;
    }
    const DWORD attributes = GetFileAttributesW(path.c_str());
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_REPARSE_POINT);
}

inline bool finalPath(HANDLE handle, std::wstring& result)
{
    const DWORD flags = FILE_NAME_NORMALIZED | VOLUME_NAME_DOS;
    const DWORD needed = GetFinalPathNameByHandleW(handle, nullptr, 0, flags);
    if (!needed || needed > 32768) return false;
    result.assign(needed + 1, L'\0');
    const DWORD count = GetFinalPathNameByHandleW(handle, result.data(), needed + 1, flags);
    if (!count || count > needed) return false;
    result.resize(count);
    return true;
}

inline std::wstring takeString(BSTR value)
{
    const std::wstring result = value ? std::wstring(value, SysStringLen(value)) : std::wstring();
    SysFreeString(value);
    return result;
}

inline bool candidate(IUIAutomationElement* element, DWORD expectedPid, bool edit,
                      std::wstring& name, std::wstring& id, HRESULT& hr, ULONGLONG deadline)
{
    if (!element || GetTickCount64() >= deadline) { hr = HRESULT_FROM_WIN32(ERROR_TIMEOUT); return false; }
    int pid = 0, type = 0;
    BOOL enabled = FALSE, offscreen = TRUE;
    if (FAILED(hr = element->get_CurrentProcessId(&pid))) return false;
    if (pid != static_cast<int>(expectedPid)) { hr = S_FALSE; return false; }
    if (GetTickCount64() >= deadline) { hr = HRESULT_FROM_WIN32(ERROR_TIMEOUT); return false; }
    if (FAILED(hr = element->get_CurrentControlType(&type))) return false;
    if (GetTickCount64() >= deadline) { hr = HRESULT_FROM_WIN32(ERROR_TIMEOUT); return false; }
    if (FAILED(hr = element->get_CurrentIsEnabled(&enabled))) return false;
    if (GetTickCount64() >= deadline) { hr = HRESULT_FROM_WIN32(ERROR_TIMEOUT); return false; }
    if (FAILED(hr = element->get_CurrentIsOffscreen(&offscreen))) return false;
    if (GetTickCount64() >= deadline) { hr = HRESULT_FROM_WIN32(ERROR_TIMEOUT); return false; }
    BSTR rawName = nullptr, rawId = nullptr;
    if (FAILED(hr = element->get_CurrentName(&rawName))) { SysFreeString(rawName); return false; }
    name = takeString(rawName);
    if (GetTickCount64() >= deadline) { hr = HRESULT_FROM_WIN32(ERROR_TIMEOUT); return false; }
    if (FAILED(hr = element->get_CurrentAutomationId(&rawId))) { SysFreeString(rawId); return false; }
    id = takeString(rawId);
    if (!enabled || offscreen || type != (edit ? UIA_EditControlTypeId : UIA_ButtonControlTypeId)) { hr = S_FALSE; return false; }
    const bool matches = edit ? (name == L"File name:" || name == L"Nom du fichier :" || id == L"1148")
                              : (id == L"1" && (name == L"Open" || name == L"Ouvrir"));
    hr = matches ? S_OK : S_FALSE;
    return matches;
}

inline HRESULT uniqueControl(IUIAutomation* automation, HWND dialog, DWORD pid, bool edit,
                             ComPtr<IUIAutomationElement>& match, std::wstring& name,
                             std::wstring& id, ULONGLONG deadline)
{
    if (GetTickCount64() >= deadline) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
    ComPtr<IUIAutomationElement> root;
    HRESULT hr = automation->ElementFromHandle(dialog, &root);
    if (FAILED(hr) || !root) return FAILED(hr) ? hr : E_POINTER;
    VARIANT type;
    VariantInit(&type);
    type.vt = VT_I4;
    type.lVal = edit ? UIA_EditControlTypeId : UIA_ButtonControlTypeId;
    ComPtr<IUIAutomationCondition> condition;
    if (FAILED(hr = automation->CreatePropertyCondition(UIA_ControlTypePropertyId, type, &condition))) return hr;
    if (GetTickCount64() >= deadline) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
    ComPtr<IUIAutomationElementArray> elements;
    if (FAILED(hr = root->FindAll(TreeScope_Descendants, condition.Get(), &elements)) || !elements) return FAILED(hr) ? hr : E_POINTER;
    int count = 0;
    if (FAILED(hr = elements->get_Length(&count))) return hr;
    if (count < 0 || count > 256) return HRESULT_FROM_WIN32(ERROR_BUFFER_OVERFLOW);
    unsigned matches = 0;
    for (int index = 0; index < count; ++index) {
        if (GetTickCount64() >= deadline) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
        ComPtr<IUIAutomationElement> element;
        if (FAILED(hr = elements->GetElement(index, &element))) return hr;
        std::wstring actualName, actualId;
        if (candidate(element.Get(), pid, edit, actualName, actualId, hr, deadline)) {
            if (++matches > 1) return HRESULT_FROM_WIN32(ERROR_DUP_NAME);
            match = element;
            name = actualName;
            id = actualId;
        } else if (FAILED(hr)) return hr;
    }
    return matches == 1 ? S_OK : HRESULT_FROM_WIN32(ERROR_NOT_FOUND);
}
}

// Selects a single already copied MSCX through the actual native file chooser.
// The caller supplies initialized UIA provider timeouts and records snapshots.
// No score file is opened for writing, moved, deleted, or executed here.
inline OwnedFileSelectionResult SelectOwnedScoreFile(
    IUIAutomation* automation, DWORD expectedPid, HANDLE process, HWND main,
    const std::wstring& fixtureRoot, const std::wstring& filePath,
    const std::function<void(const wchar_t*)>& snapshotBeforeOrAfter)
{
    using namespace cadence_owned_file_dialog_detail;
    OwnedFileSelectionResult result;
    const ULONGLONG deadline = GetTickCount64() + 12000;
    if (!automation || !snapshotBeforeOrAfter || !alive(expectedPid, process) || !owned(main, expectedPid))
        return fail(result, L"Blocked: UIA, snapshot callback or owned live process is unavailable.", E_INVALIDARG);

    std::wstring rootPath, selectedPath;
    if (!fullLocalPath(fixtureRoot, rootPath) || !fullLocalPath(filePath, selectedPath)
        || selectedPath.size() < 5 || !sameText(selectedPath.substr(selectedPath.size() - 5), L".mscx")
        || !noReparseComponents(rootPath, deadline) || !noReparseComponents(selectedPath, deadline))
        return fail(result, L"Blocked: fixture must be an existing local absolute MSCX path without reparse components.", E_ACCESSDENIED);
    ReadHandle rootHandle, fileHandle;
    rootHandle.value = CreateFileW(rootPath.c_str(), FILE_READ_ATTRIBUTES,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING,
                                  FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    fileHandle.value = CreateFileW(selectedPath.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                                  FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (rootHandle.value == INVALID_HANDLE_VALUE || fileHandle.value == INVALID_HANDLE_VALUE)
        return fail(result, L"Blocked: copied fixture or its controlled root cannot be opened read-only.", E_ACCESSDENIED, GetLastError());
    BY_HANDLE_FILE_INFORMATION rootInfo {}, fileInfo {};
    std::wstring finalRoot, finalFile;
    if (!GetFileInformationByHandle(rootHandle.value, &rootInfo) || !GetFileInformationByHandle(fileHandle.value, &fileInfo)
        || !(rootInfo.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
        || (rootInfo.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)
        || (fileInfo.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))
        || GetFileType(fileHandle.value) != FILE_TYPE_DISK
        || !finalPath(rootHandle.value, finalRoot) || !finalPath(fileHandle.value, finalFile))
        return fail(result, L"Blocked: fixture handles do not identify ordinary controlled paths.", E_ACCESSDENIED, GetLastError());
    while (!finalRoot.empty() && finalRoot.back() == L'\\') finalRoot.pop_back();
    finalRoot += L'\\';
    if (finalFile.size() <= finalRoot.size() || !sameText(finalFile.substr(0, finalRoot.size()), finalRoot))
        return fail(result, L"Blocked: fixture is outside the real controlled-root boundary.", E_ACCESSDENIED);

    auto contextValid = [&]() {
        return GetTickCount64() < deadline && alive(expectedPid, process) && owned(main, expectedPid)
               && isDialog(result.dialog, main, expectedPid);
    };
    auto snapshot = [&](const wchar_t* phase) {
        if (GetTickCount64() >= deadline) return false;
        try { snapshotBeforeOrAfter(phase); }
        catch (...) { result.diagnostic = L"Blocked: evidence snapshot callback failed."; return false; }
        return GetTickCount64() < deadline;
    };
    while (GetTickCount64() < deadline && alive(expectedPid, process) && owned(main, expectedPid)) {
        DialogSearch search { main, expectedPid, deadline };
        EnumWindows(inspectDialog, reinterpret_cast<LPARAM>(&search));
        if (search.count > 1) return fail(result, L"Blocked: multiple matching owned file dialogs.", HRESULT_FROM_WIN32(ERROR_DUP_NAME));
        if (search.count == 1) { result.dialog = search.match; break; }
        waitBriefly(deadline);
    }
    if (!result.dialog || !contextValid()) return fail(result, L"Blocked: exact owned native library file dialog was not found.", HRESULT_FROM_WIN32(ERROR_TIMEOUT));

    ComPtr<IUIAutomationElement> edit;
    std::wstring editId;
    result.editDiscovery = uniqueControl(automation, result.dialog, expectedPid, true, edit,
                                        result.editName, editId, deadline);
    result.editAutomationId = editId;
    if (FAILED(result.editDiscovery)) return fail(result, L"Blocked: filename Edit is absent, unavailable or ambiguous.", result.editDiscovery);
    ComPtr<IUIAutomationValuePattern> value;
    result.valuePattern = edit->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&value));
    if (FAILED(result.valuePattern) || !value) return fail(result, L"Blocked: filename Edit has no writable ValuePattern.", FAILED(result.valuePattern) ? result.valuePattern : E_POINTER);
    BOOL readOnly = TRUE;
    result.readOnlyState = value->get_CurrentIsReadOnly(&readOnly);
    if (FAILED(result.readOnlyState) || readOnly) return fail(result, L"Blocked: filename ValuePattern is read-only or unavailable.", FAILED(result.readOnlyState) ? result.readOnlyState : E_ACCESSDENIED);
    if (!snapshot(L"file-dialog-before-set-value") || !contextValid())
        return fail(result, L"Blocked: file-dialog context/evidence changed before SetValue.", E_ACCESSDENIED);
    HRESULT candidateResult = E_FAIL;
    std::wstring currentName, currentId;
    if (!candidate(edit.Get(), expectedPid, true, currentName, currentId, candidateResult, deadline) || !contextValid())
        return fail(result, L"Blocked: filename Edit changed before SetValue.", E_ACCESSDENIED);
    result.setValue = value->SetValue(selectedPath.c_str());
    result.valueSet = SUCCEEDED(result.setValue);
    if (!result.valueSet) return fail(result, L"Blocked: setting the copied fixture path failed.", result.setValue);
    if (!snapshot(L"file-dialog-after-set-value") || !contextValid())
        return fail(result, L"Blocked: file-dialog context/evidence changed after SetValue.", E_ACCESSDENIED);
    BSTR currentValue = nullptr;
    result.readValue = value->get_CurrentValue(&currentValue);
    const std::wstring actualValue = takeString(currentValue);
    result.valueVerified = SUCCEEDED(result.readValue) && sameText(actualValue, selectedPath);
    if (!result.valueVerified) return fail(result, L"Blocked: filename ValuePattern did not retain the exact copied absolute path.", FAILED(result.readValue) ? result.readValue : E_FAIL);
    result.verifiedPath = selectedPath;

    ComPtr<IUIAutomationElement> button;
    std::wstring buttonId;
    result.buttonDiscovery = uniqueControl(automation, result.dialog, expectedPid, false, button,
                                          result.buttonName, buttonId, deadline);
    result.buttonAutomationId = buttonId;
    if (FAILED(result.buttonDiscovery)) return fail(result, L"Blocked: unique Open/Ouvrir button with AutomationId1 is unavailable.", result.buttonDiscovery);
    ComPtr<IUIAutomationInvokePattern> invoke;
    result.invokePattern = button->GetCurrentPatternAs(UIA_InvokePatternId, IID_PPV_ARGS(&invoke));
    if (FAILED(result.invokePattern) || !invoke) return fail(result, L"Blocked: file-dialog Open button has no InvokePattern.", FAILED(result.invokePattern) ? result.invokePattern : E_POINTER);
    if (!snapshot(L"file-dialog-before-invoke-open") || !contextValid()
        || !candidate(button.Get(), expectedPid, false, currentName, currentId, candidateResult, deadline) || !contextValid())
        return fail(result, L"Blocked: exact owned Open button changed before Invoke.", E_ACCESSDENIED);
    // The evidence callback or dialog's own asynchronous work may have changed
    // its field. Never confirm a different path after an earlier successful read.
    currentValue = nullptr;
    result.readValue = value->get_CurrentValue(&currentValue);
    const std::wstring valueBeforeInvoke = takeString(currentValue);
    result.valueVerified = SUCCEEDED(result.readValue) && sameText(valueBeforeInvoke, selectedPath);
    if (!result.valueVerified || !contextValid())
        return fail(result, L"Blocked: copied absolute path changed before Open Invoke.", FAILED(result.readValue) ? result.readValue : E_ACCESSDENIED);
    result.invokeRequested = true;
    result.invoke = invoke->Invoke();
    if (FAILED(result.invoke)) return fail(result, L"Blocked: invoking the owned Open button failed.", result.invoke);
    if (!snapshot(L"file-dialog-after-invoke-open"))
        return fail(result, L"Blocked: post-Invoke evidence unavailable or deadline reached.", HRESULT_FROM_WIN32(ERROR_TIMEOUT));
    while (GetTickCount64() < deadline && alive(expectedPid, process) && owned(main, expectedPid)) {
        result.dialogClosed = !IsWindow(result.dialog) || !IsWindowVisible(result.dialog);
        result.mainEnabled = IsWindowEnabled(main) != FALSE;
        if (result.dialogClosed && result.mainEnabled) {
            result.selected = true;
            result.result = S_OK;
            result.diagnostic = L"Copied MSCX selected through owned native Value/Invoke; dialog closed and main enabled. Library import remains to be observed.";
            return result;
        }
        waitBriefly(deadline);
    }
    return fail(result, L"Blocked: native chooser did not close and enable the owned main before the deadline.", HRESULT_FROM_WIN32(ERROR_TIMEOUT));
}
