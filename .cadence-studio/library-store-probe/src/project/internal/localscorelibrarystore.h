// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <QList>
#include <QString>

#include <functional>

namespace mu::project {
struct LocalLibraryEntry {
    QString id;
    QString path;
    QString title;
    QString composer;
    bool favorite = false;
};

struct LocalLibraryResult {
    bool ok = false;
    QString error;
    QList<LocalLibraryEntry> entries;
};

// Owns only the catalogue, never the score files referenced by it. Every mutation
// re-reads the catalogue under the same interprocess lock used for its commit.
// An invalid or newer catalogue is returned as an error, never reset to empty.
class LocalScoreLibraryStore
{
public:
    explicit LocalScoreLibraryStore(QString filePath);

    LocalLibraryResult load() const;
    LocalLibraryResult add(const QList<LocalLibraryEntry>& entries);
    LocalLibraryResult setFavorite(const QString& id, bool favorite);
    LocalLibraryResult remove(const QString& id);
    LocalLibraryResult relink(const QString& id, const LocalLibraryEntry& replacement);
    QString filePath() const;

private:
    using Mutation = std::function<bool(QList<LocalLibraryEntry>&, QString&)>;
    LocalLibraryResult mutate(const Mutation& mutation);
    LocalLibraryResult readUnlocked() const;

    QString m_filePath;
};
}
