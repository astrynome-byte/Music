// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QString>

#ifdef Q_OS_WIN
#include <QScopeGuard>
#include <qt_windows.h>
#include <array>
#include <cstddef>
#include <cstring>
#endif

namespace mu::project {
#ifdef Q_OS_WIN
// Query the entry through its parent directory, never through an open data
// handle to the catalogue. A fresh file id distinguishes atomic replacements
// even when Qt's Windows watcher filters equal size/time/permissions.
inline QString localCatalogWindowsIdentity(const QFileInfo& info)
{
    QString parent = QDir::toNativeSeparators(QDir::cleanPath(info.absolutePath()));
    if (!parent.startsWith(QStringLiteral("\\\\?\\"))) {
        parent = parent.startsWith(QStringLiteral("\\\\"))
                 ? QStringLiteral("\\\\?\\UNC\\") + parent.mid(2)
                 : QStringLiteral("\\\\?\\") + parent;
    }
    HANDLE directory = CreateFileW(reinterpret_cast<LPCWSTR>(parent.utf16()),
                                   FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES,
                                   FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                   nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
    if (directory == INVALID_HANDLE_VALUE) {
        return {};
    }
    const auto close = qScopeGuard([directory]() { CloseHandle(directory); });
    BY_HANDLE_FILE_INFORMATION parentInfo {};
    if (!GetFileInformationByHandle(directory, &parentInfo)) {
        return {};
    }
    constexpr size_t HeaderSize = offsetof(FILE_ID_BOTH_DIR_INFO, FileName);
    alignas(FILE_ID_BOTH_DIR_INFO) std::array<unsigned char, 16384> buffer {};
    for (int batch = 0; batch < 64; ++batch) {
        const auto infoClass = batch == 0 ? FileIdBothDirectoryRestartInfo : FileIdBothDirectoryInfo;
        if (!GetFileInformationByHandleEx(directory, infoClass, buffer.data(), DWORD(buffer.size()))) {
            return {}; // Unsupported filesystem, absent entry, or bounded query failure.
        }
        size_t offset = 0;
        while (offset <= buffer.size() - HeaderSize) {
            FILE_ID_BOTH_DIR_INFO entry {};
            std::memcpy(&entry, buffer.data() + offset, HeaderSize);
            const size_t available = buffer.size() - offset;
            const size_t span = entry.NextEntryOffset ? entry.NextEntryOffset : available;
            if (span < HeaderSize || span > available || !entry.FileNameLength
                || entry.FileNameLength % sizeof(wchar_t)
                || entry.FileNameLength > span - HeaderSize
                || (entry.NextEntryOffset && entry.NextEntryOffset % alignof(FILE_ID_BOTH_DIR_INFO))) {
                return {};
            }
            const auto* name = reinterpret_cast<const wchar_t*>(buffer.data() + offset + HeaderSize);
            if (QString::fromWCharArray(name, int(entry.FileNameLength / sizeof(wchar_t)))
                .compare(info.fileName(), Qt::CaseInsensitive) == 0) {
                if (!entry.FileId.QuadPart) {
                    return {}; // A zero id cannot distinguish these entries reliably.
                }
                return QString::number(parentInfo.dwVolumeSerialNumber, 16) + QLatin1Char(':')
                       + QString::number(static_cast<qulonglong>(entry.FileId.QuadPart), 16);
            }
            if (!entry.NextEntryOffset) {
                break;
            }
            offset += entry.NextEntryOffset;
        }
    }
    return {}; // A large directory must not cause an unbounded GUI-thread scan.
}
#endif

// Directory-notification filter. Windows watches only the parent: Qt's file
// PathInfo metadata polling can race QSaveFile replacement outside our lock.
// The parent entry id detects equal-metadata atomic replacements without a
// target handle. Other platforms retain native file events for the metadata-only
// fallback; unsupported Windows identities still use metadata/manual refresh.
inline QString localCatalogMetadataStamp(const QString& path)
{
    const QFileInfo info(path);
    if (!info.exists()) {
        return QStringLiteral("missing");
    }
    QString stamp = QString::number(info.size()) + QLatin1Char(':')
                    + QString::number(info.lastModified().toMSecsSinceEpoch()) + QLatin1Char(':')
                    + QString::number(info.isFile());
#ifdef Q_OS_WIN
    const QString identity = localCatalogWindowsIdentity(info);
    stamp += identity.isEmpty() ? QStringLiteral(":identity-unavailable") : QLatin1Char(':') + identity;
#endif
    return stamp;
}

inline void watchLocalCatalog(QFileSystemWatcher& watcher, const QString& path)
{
    const QFileInfo info(path);
    const QString parent = info.absolutePath();
#ifdef Q_OS_WIN
    // Remove an older registration too; do not leave a native file watcher
    // querying the target while another process commits under QLockFile.
    if (watcher.files().contains(path)) {
        watcher.removePath(path);
    }
#endif
    if (QDir(parent).exists() && !watcher.directories().contains(parent)) {
        watcher.addPath(parent);
    }
#ifndef Q_OS_WIN
    if (info.exists() && !watcher.files().contains(path)) {
        watcher.addPath(path);
    }
#endif
}
}
