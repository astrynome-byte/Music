// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "OwnedKeyboard.h"

// Narrow extension of the existing owned keyboard primitive for this one score
// exercise. Caller proves live UIA focus belongs to the score before each call.
enum class ScoreKey { first, noteInput, quarter, c, d, e, f, escape, save, undo, redo };
inline bool ExactScoreMainContext(HWND main,const OwnedKeyResult& result)
{
    return main && GetAncestor(main,GA_ROOTOWNER)==main
        && GetAncestor(result.foreground,GA_ROOT)==main
        && GetAncestor(result.foreground,GA_ROOTOWNER)==main
        && GetAncestor(result.focus,GA_ROOT)==main
        && GetAncestor(result.focus,GA_ROOTOWNER)==main;
}
inline OwnedKeyResult SendOwnedScoreKey(DWORD expectedPid, HANDLE process, HWND main, ScoreKey action)
{
    using namespace cadence_owned_keyboard_detail;
    OwnedKeyResult result;
    WORD key = 0; bool control = false;
    switch (action) {
    case ScoreKey::first: key = VK_HOME; control = true; break;
    case ScoreKey::noteInput: key = 'N'; break;
    case ScoreKey::quarter: key = '5'; break;
    case ScoreKey::c: key = 'C'; break;
    case ScoreKey::d: key = 'D'; break;
    case ScoreKey::e: key = 'E'; break;
    case ScoreKey::f: key = 'F'; break;
    case ScoreKey::escape: key = VK_ESCAPE; break;
    case ScoreKey::save: key = 'S'; control = true; break;
    case ScoreKey::undo: key = 'Z'; control = true; break;
    case ScoreKey::redo: key = 'Y'; control = true; break;
    default: result.error = ERROR_INVALID_PARAMETER; return result;
    }
    // No mouse, command URI, Qt engine, hooks or AttachThreadInput. The previous
    // navigation primitive already established foreground; this one never steals it.
    if (!processAlive(expectedPid,process,result.error) || !windowOwned(main,expectedPid)
        || !IsWindowEnabled(main) || modifiersDown() || !sampleOwnedFocus(expectedPid,result)
        || !ExactScoreMainContext(main,result)) {
        if (!result.error) result.error = ERROR_ACCESS_DENIED;
        return result;
    }
    const HWND observedForeground = result.foreground, observedFocus = result.focus;
    INPUT inputs[4] {}; UINT count = 0;
    auto insert = [&](WORD value,DWORD flags) { auto& input=inputs[count++];input.type=INPUT_KEYBOARD;input.ki.wVk=value;input.ki.dwFlags=flags; };
    if (control) insert(VK_CONTROL,0);
    const DWORD flags = key == VK_HOME ? KEYEVENTF_EXTENDEDKEY : 0;
    insert(key,flags); insert(key,flags|KEYEVENTF_KEYUP);
    if (control) insert(VK_CONTROL,KEYEVENTF_KEYUP);
    if (!processAlive(expectedPid,process,result.error) || !windowOwned(main,expectedPid)
        || !IsWindowEnabled(main) || modifiersDown() || !sampleOwnedFocus(expectedPid,result)
        || !ExactScoreMainContext(main,result)
        || result.foreground != observedForeground || result.focus != observedFocus
        || GetForegroundWindow() != result.foreground || !windowOwned(result.focus,expectedPid)) {
        if (!result.error) result.error = ERROR_ACCESS_DENIED;
        return result;
    }
    SetLastError(ERROR_SUCCESS);
    result.inputCount=SendInput(count,inputs,sizeof(INPUT));result.error=GetLastError();result.sent=result.inputCount==count;
    // Partial insertion is fatal. Never replay or send compensating keys.
    return result;
}
