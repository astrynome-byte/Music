// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "qa_clock_api.h"
#include <string>

namespace cadence::qa {
inline std::wstring environment(const wchar_t* name) {
    wchar_t value[32768] {};
    const DWORD size = GetEnvironmentVariableW(name, value, 32768);
    return size && size < 32768 ? std::wstring(value, size) : std::wstring();
}
inline bool below(const std::wstring& child, const std::wstring& parent) {
    return child.size() > parent.size() + 1 && child[parent.size()] == L'\\'
        && CompareStringOrdinal(child.data(), static_cast<int>(parent.size()), parent.data(),
                                static_cast<int>(parent.size()), TRUE) == CSTR_EQUAL;
}
inline bool plainDirectory(const std::wstring& input, std::wstring& full) {
    if (input.empty() || input.find_first_of(L"\r\n") != std::wstring::npos) { return false; }
    wchar_t expanded[32768] {};
    const DWORD length = GetFullPathNameW(input.c_str(), 32768, expanded, nullptr);
    if (!length || length >= 32768) { return false; }
    full.assign(expanded, length);
    while (full.size() > 3 && full.back() == L'\\') { full.pop_back(); }
    const DWORD rootAttributes = GetFileAttributesW(full.c_str());
    if (rootAttributes == INVALID_FILE_ATTRIBUTES || !(rootAttributes & FILE_ATTRIBUTE_DIRECTORY)) { return false; }
    std::wstring current = full;
    while (current.size() > 3) {
        const DWORD attributes = GetFileAttributesW(current.c_str());
        if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) { return false; }
        const auto split = current.find_last_of(L'\\');
        if (split == std::wstring::npos) { return false; }
        current.resize(split);
    }
    // Only drive-rooted local paths, not UNC/device namespaces.
    return full.size() > 3 && full[1] == L':' && full[2] == L'\\' && full[0] != L'\\';
}
inline bool disposableCi(std::wstring* statsDirectory = nullptr) {
    if (sizeof(void*) != 8 || environment(L"GITHUB_ACTIONS") != L"true"
        || environment(L"CI") != L"true" || environment(L"RUNNER_ENVIRONMENT") != L"github-hosted") { return false; }
    std::wstring temporary, stats;
    if (!plainDirectory(environment(L"RUNNER_TEMP"), temporary)
        || !plainDirectory(environment(L"CADENCE_QA_CLOCK_STATS_DIR"), stats) || !below(stats, temporary)) { return false; }
    if (statsDirectory) { *statsDirectory = stats; }
    return true;
}
}
