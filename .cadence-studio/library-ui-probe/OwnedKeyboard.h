// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <windows.h>

struct OwnedKeyResult {
    bool sent = false;
    DWORD error = 0;
    HWND foreground = nullptr;
    HWND focus = nullptr;
    UINT inputCount = 0;
};

namespace cadence_owned_keyboard_detail {
inline bool processAlive(DWORD expectedPid, HANDLE process, DWORD& error)
{
    if (!expectedPid || !process || process == INVALID_HANDLE_VALUE) {
        error = ERROR_INVALID_PARAMETER;
        return false;
    }
    DWORD exitCode = 0;
    if (!GetExitCodeProcess(process, &exitCode)) {
        error = GetLastError();
        return false;
    }
    if (exitCode != STILL_ACTIVE) {
        error = ERROR_PROCESS_ABORTED;
        return false;
    }
    const DWORD processId = GetProcessId(process);
    if (!processId) {
        error = GetLastError();
        return false;
    }
    if (processId != expectedPid) {
        error = ERROR_ACCESS_DENIED;
        return false;
    }
    // An exit status of 259 alone is ambiguous. The process handle must also
    // remain unsignalled; the caller supplies QUERY_LIMITED_INFORMATION|SYNCHRONIZE.
    const DWORD wait = WaitForSingleObject(process, 0);
    if (wait != WAIT_TIMEOUT) {
        error = wait == WAIT_FAILED ? GetLastError() : ERROR_PROCESS_ABORTED;
        return false;
    }
    return true;
}

inline bool windowOwned(HWND window, DWORD expectedPid)
{
    DWORD pid = 0;
    return window && GetWindowThreadProcessId(window, &pid) != 0 && pid == expectedPid;
}

inline bool modifiersDown()
{
    const int modifiers[] { VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
                            VK_MENU, VK_LMENU, VK_RMENU,
                            VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_LWIN, VK_RWIN };
    for (const int key : modifiers) {
        if ((GetAsyncKeyState(key) & 0x8000) != 0) {
            return true;
        }
    }
    return false;
}

inline bool sampleOwnedFocus(DWORD expectedPid, OwnedKeyResult& result)
{
    result.foreground = GetForegroundWindow();
    result.focus = nullptr;
    DWORD pid = 0;
    const DWORD thread = result.foreground ? GetWindowThreadProcessId(result.foreground, &pid) : 0;
    if (!thread || pid != expectedPid) {
        result.error = ERROR_ACCESS_DENIED;
        return false;
    }
    GUITHREADINFO gui {};
    gui.cbSize = static_cast<DWORD>(sizeof(gui));
    if (!GetGUIThreadInfo(thread, &gui)) {
        result.error = GetLastError();
        return false;
    }
    result.focus = gui.hwndFocus;
    if (!windowOwned(result.focus, expectedPid)) {
        result.error = ERROR_ACCESS_DENIED;
        return false;
    }
    return true;
}
}

// The caller records an accessibility tree before and after this one semantic
// navigation key. No text, modifiers, mouse messages or process cleanup occurs.
// SendInput cannot be atomically addressed to a PID: foreground and focus are
// checked again immediately before insertion, and mismatches always stop it.
inline OwnedKeyResult SendOwnedKey(DWORD expectedPid, HANDLE process, HWND main, WORD virtualKey)
{
    using namespace cadence_owned_keyboard_detail;
    OwnedKeyResult result;
    if (virtualKey != VK_F6 && virtualKey != VK_TAB && virtualKey != VK_RIGHT && virtualKey != VK_DOWN && virtualKey != VK_RETURN) {
        result.error = ERROR_INVALID_PARAMETER;
        return result;
    }
    if (!processAlive(expectedPid, process, result.error)) {
        return result;
    }
    if (!windowOwned(main, expectedPid) || !IsWindowEnabled(main)) {
        result.error = ERROR_ACCESS_DENIED;
        return result;
    }
    if (modifiersDown()) {
        result.error = ERROR_BUSY;
        return result;
    }

    result.foreground = GetForegroundWindow();
    if (!windowOwned(result.foreground, expectedPid)) {
        // Foreground activation may be denied by Windows. Never compensate with
        // AttachThreadInput, a modifier key, a click, or a global keyboard hook.
        const ULONGLONG started = GetTickCount64();
        SetForegroundWindow(main);
        for (;;) {
            result.foreground = GetForegroundWindow();
            if (windowOwned(result.foreground, expectedPid)) {
                break;
            }
            if (!processAlive(expectedPid, process, result.error)) {
                return result;
            }
            const ULONGLONG elapsed = GetTickCount64() - started;
            if (elapsed >= 150) {
                result.error = ERROR_ACCESS_DENIED;
                return result;
            }
            const DWORD remaining = static_cast<DWORD>(150 - elapsed);
            Sleep(remaining < 5 ? remaining : 5);
        }
    }
    if (!sampleOwnedFocus(expectedPid, result)) {
        return result;
    }

    INPUT inputs[2] {};
    inputs[0].type = INPUT_KEYBOARD;
    inputs[0].ki.wVk = virtualKey;
    inputs[0].ki.dwFlags = virtualKey == VK_RIGHT || virtualKey == VK_DOWN ? KEYEVENTF_EXTENDEDKEY : 0;
    inputs[1] = inputs[0];
    inputs[1].ki.dwFlags |= KEYEVENTF_KEYUP;

    // Re-read live state; do not trust any HWND/focus captured for the tree.
    if (!processAlive(expectedPid, process, result.error) ||
        !windowOwned(main, expectedPid) || !IsWindowEnabled(main)) {
        if (!result.error) {
            result.error = ERROR_ACCESS_DENIED;
        }
        return result;
    }
    if (modifiersDown()) {
        result.error = ERROR_BUSY;
        return result;
    }
    if (!sampleOwnedFocus(expectedPid, result)) {
        return result;
    }
    // Catch a focus/activation change that occurred during GetGUIThreadInfo.
    if (GetForegroundWindow() != result.foreground || !windowOwned(result.focus, expectedPid)) {
        result.error = ERROR_ACCESS_DENIED;
        return result;
    }

    SetLastError(ERROR_SUCCESS);
    result.inputCount = SendInput(2, inputs, static_cast<int>(sizeof(INPUT)));
    result.error = GetLastError();
    result.sent = result.inputCount == 2;
    // In particular, count 0/1 with last-error 0 is still a failure. No retry
    // or extra key-up is sent after a partial insertion to a changed desktop.
    return result;
}
