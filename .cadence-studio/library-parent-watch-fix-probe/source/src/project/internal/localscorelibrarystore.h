// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <QList>
#include <QString>
#include <QStringList>

#include <functional>

namespace mu::project {
struct LocalLibraryEntry {
    QString id;
    QString path;
    QString title;
    QString composer;
    bool favorite = false;
};

struct LocalLibraryCollection {
    QString id;
    QString name;
    QStringList entryIds;
};

struct LocalLibraryAnnotation {
    QString id;
    QString entryId;
    QString text;
    int measure = 0; // Zero means no manual reference; these are not layout anchors.
    int page = 0;
    int revision = 1;
};

struct LocalLibraryResult {
    bool ok = false;
    QString error;
    QList<LocalLibraryEntry> entries;
    int schemaVersion = 1;
    QList<LocalLibraryCollection> collections {};
    QList<LocalLibraryAnnotation> annotations {};
    QString migrationBackupPath {}; // Transient result, not part of the catalogue.
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
    LocalLibraryResult remove(const QString& id, const QList<LocalLibraryAnnotation>& expectedNotes = {});
    LocalLibraryResult relink(const QString& id, const LocalLibraryEntry& replacement);
    // An explicit opt-in is the only operation that upgrades schema 1 to 2.
    // Older Cadence readers refuse schema 2 without rewriting its catalogue.
    LocalLibraryResult enableCollections();
    LocalLibraryResult createCollection(const QString& name);
    LocalLibraryResult renameCollection(const QString& id, const QString& name);
    LocalLibraryResult removeCollection(const QString& id);
    LocalLibraryResult setCollectionEntry(const QString& collectionId, const QString& entryId, bool included);
    LocalLibraryResult moveCollectionEntry(const QString& collectionId, const QString& entryId, int offset);
    // Explicit opt-in; copies the previous catalogue before the first schema 3 commit.
    LocalLibraryResult enableAnnotations();
    LocalLibraryResult addAnnotation(const QString& entryId, const QString& text, int measure = 0, int page = 0);
    LocalLibraryResult editAnnotation(const QString& id, int expectedRevision, const QString& text, int measure = 0, int page = 0);
    LocalLibraryResult removeAnnotation(const QString& id, int expectedRevision);
    QString filePath() const;

private:
    using Mutation = std::function<bool(LocalLibraryResult&, QString&)>;
    LocalLibraryResult mutate(const Mutation& mutation);
    LocalLibraryResult readUnlocked() const;

    QString m_filePath;
};
}
