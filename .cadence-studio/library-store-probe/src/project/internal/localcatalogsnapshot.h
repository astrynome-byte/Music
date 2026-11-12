// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <QDir>
#include <QFile>
#include <QFileInfo>

#ifdef Q_OS_WIN
#include <qt_windows.h>
#include <fcntl.h>
#include <io.h>
#endif

namespace mu::project {
// A read-only catalogue snapshot must not prevent QSaveFile from atomically
// replacing that catalogue in another worker/window. Qt's normal Windows
// QFile open shares reads/writes, but not deletion/replacement. Adopt a CRT
// descriptor whose underlying handle also shares DELETE; QFile owns it only
// after a successful open. No score file is opened by this helper.
inline bool openLocalLibrarySnapshot(QFile& file, const QString& absolutePath)
{
    if (file.isOpen() || !QFileInfo(absolutePath).isAbsolute()) {
        return false;
    }
#ifdef Q_OS_WIN
    QString nativePath = QDir::toNativeSeparators(QDir::cleanPath(absolutePath));
    // Preserve Unicode, UNC and long absolute paths without depending on the
    // machine's MAX_PATH policy. The input is already an absolute, clean path.
    if (!nativePath.startsWith(QStringLiteral("\\\\?\\"))) {
        nativePath = nativePath.startsWith(QStringLiteral("\\\\"))
                     ? QStringLiteral("\\\\?\\UNC\\") + nativePath.mid(2)
                     : QStringLiteral("\\\\?\\") + nativePath;
    }
    HANDLE handle = CreateFileW(reinterpret_cast<LPCWSTR>(nativePath.utf16()), GENERIC_READ,
                                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) {
        return false;
    }
    const int descriptor = _open_osfhandle(reinterpret_cast<intptr_t>(handle), _O_RDONLY | _O_BINARY);
    if (descriptor == -1) {
        CloseHandle(handle);
        return false;
    }
    if (!file.open(descriptor, QIODevice::ReadOnly, QFileDevice::AutoCloseHandle)) {
        _close(descriptor); // The CRT descriptor owns the native handle now.
        return false;
    }
    return true;
#else
    file.setFileName(absolutePath);
    return file.open(QIODevice::ReadOnly);
#endif
}
}
