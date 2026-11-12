// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QString>

namespace mu::project {
// Only a directory-notification filter: native file notifications always force
// a refresh, including replacements with equal size and timestamp. No catalogue
// data stream is opened, so this cannot deny the store's atomic Windows save.
inline QString localCatalogMetadataStamp(const QString& path)
{
    const QFileInfo info(path);
    if (!info.exists()) {
        return QStringLiteral("missing");
    }
    return QString::number(info.size()) + QLatin1Char(':')
           + QString::number(info.lastModified().toMSecsSinceEpoch()) + QLatin1Char(':')
           + QString::number(info.isFile());
}

inline void watchLocalCatalog(QFileSystemWatcher& watcher, const QString& path)
{
    const QFileInfo info(path);
    const QString parent = info.absolutePath();
    if (QDir(parent).exists() && !watcher.directories().contains(parent)) {
        watcher.addPath(parent);
    }
    if (info.exists() && !watcher.files().contains(path)) {
        watcher.addPath(path);
    }
}
}
