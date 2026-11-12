// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#include "localscorelibrarystore.h"
#include "localcatalogwatch.h"
#include "localscorexmlcheck.h"

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QDateTime>
#include <QEventLoop>
#include <QFileSystemWatcher>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLockFile>
#include <QProcess>
#include <QTemporaryDir>
#include <QThread>
#include <QTimeZone>
#include <QUuid>

#include <functional>
#include <iostream>
#include <stdexcept>

using namespace mu::project;

namespace {
void require(bool condition, const char* detail)
{
    if (!condition) {
        throw std::runtime_error(detail);
    }
}

QByteArray read(const QString& path)
{
    QFile file(path);
    require(file.open(QIODevice::ReadOnly), "Cannot read test file");
    return file.readAll();
}

void write(const QString& path, const QByteArray& bytes)
{
    require(QDir().mkpath(QFileInfo(path).absolutePath()), "Cannot create fixture directory");
    QFile file(path);
    require(file.open(QIODevice::WriteOnly), "Cannot write test file");
    require(file.write(bytes) == bytes.size(), "Short fixture write");
}

LocalLibraryEntry fixture(const QString& root, const QString& fileName, const QString& title = QStringLiteral("Titre français"))
{
    LocalLibraryEntry entry;
    entry.path = root + QLatin1Char('/') + fileName;
    entry.title = title;
    entry.composer = QStringLiteral("Élise Dupré");
    write(entry.path, QByteArray("Original test score bytes; the catalogue must never change them."));
    return entry;
}

QByteArray digest(const QString& path)
{
    return QCryptographicHash::hash(read(path), QCryptographicHash::Sha256);
}

void persistAndDeduplicate()
{
    QTemporaryDir temporary;
    require(temporary.isValid(), "Temporary directory unavailable");
    const auto score = fixture(temporary.path(), QString::fromUtf8("Partitions été/Étude.mscx"));
    const QByteArray original = digest(score.path);
    LocalScoreLibraryStore store(temporary.path() + QStringLiteral("/profile/library.json"));
    require(store.load().ok && store.load().entries.isEmpty(), "New catalogue must load empty");
    auto result = store.add({ score });
    require(result.ok && result.entries.size() == 1, "Add native score failed");
    const QString id = result.entries.front().id;
    require(!QUuid(id).isNull(), "Entry needs a stable UUID");
    require(store.setFavorite(id, true).ok, "Set favourite failed");
    LocalScoreLibraryStore reopened(store.filePath());
    result = reopened.load();
    require(result.ok && result.entries.size() == 1 && result.entries.front().id == id
            && result.entries.front().favorite && result.entries.front().title == score.title
            && result.entries.front().composer == score.composer, "Reopening lost metadata, id or favourite");
    auto alias = score;
    alias.path = QFileInfo(score.path).absolutePath() + QStringLiteral("/../Partitions été/Étude.mscx");
    alias.title = QStringLiteral("Must not overwrite existing metadata");
    result = reopened.add({ score, alias });
    require(result.ok && result.entries.size() == 1 && result.entries.front().id == id
            && result.entries.front().favorite && result.entries.front().title == score.title, "Duplicate add replaced existing entry");
#ifndef Q_OS_WIN
    alias.path = temporary.path() + QStringLiteral("/alias.mscx");
    require(QFile::link(score.path, alias.path), "Cannot create test score alias");
    require(reopened.add({ alias }).entries.size() == 1, "Canonical score alias was duplicated");
#else
    alias.path = score.path.toUpper();
    require(reopened.add({ alias }).entries.size() == 1, "Windows case alias was duplicated");
#endif
    require(reopened.remove(id).ok && reopened.load().entries.isEmpty(), "Remove catalogue entry failed");
    require(digest(score.path) == original, "Catalogue operations changed the score");
}

void retainAndRelinkMissing()
{
    QTemporaryDir temporary;
    auto oldScore = fixture(temporary.path(), QStringLiteral("old.mscz"));
    auto newScore = fixture(temporary.path(), QStringLiteral("elsewhere/new.mscz"), QStringLiteral("New title"));
    const QByteArray newOriginal = digest(newScore.path);
    LocalScoreLibraryStore store(temporary.path() + QStringLiteral("/library.json"));
    auto result = store.add({ oldScore });
    require(result.ok, "Initial add failed");
    const QString id = result.entries.front().id;
    require(store.setFavorite(id, true).ok, "Initial favourite failed");
    require(QFile::remove(oldScore.path), "Cannot remove own temporary test fixture");
    result = store.load();
    require(result.ok && result.entries.size() == 1 && result.entries.front().path == oldScore.path
            && result.entries.front().favorite, "Missing score reference was silently dropped");
    result = store.relink(id, newScore);
    require(result.ok && result.entries.size() == 1 && result.entries.front().path == newScore.path
            && result.entries.front().id == id && result.entries.front().favorite
            && result.entries.front().title == newScore.title, "Relocation lost identity, favourite or metadata");
    require(digest(newScore.path) == newOriginal && !QFileInfo(oldScore.path).exists(), "Relink moved or rewrote a score");
}

void rejectInvalidBatchAndCollision()
{
    QTemporaryDir temporary;
    const auto first = fixture(temporary.path(), QStringLiteral("one/score.mscx"));
    const auto second = fixture(temporary.path(), QStringLiteral("two/score.mscx"));
    const auto invalid = fixture(temporary.path(), QStringLiteral("not-a-native-score.txt"));
    LocalScoreLibraryStore store(temporary.path() + QStringLiteral("/library.json"));
    require(store.add({ first }).ok, "Initial add failed");
    const QByteArray snapshot = read(store.filePath());
    require(!store.add({ second, invalid }).ok, "Batch with unsupported file accepted");
    require(read(store.filePath()) == snapshot, "Partial batch overwrote the catalogue");
    auto missing = second;
    missing.path = temporary.path() + QStringLiteral("/disconnected/missing.mscx");
    require(!store.add({ second, missing }).ok, "Batch with missing selected file accepted");
    require(read(store.filePath()) == snapshot, "Missing-file batch overwrote the catalogue");
    auto result = store.add({ second });
    require(result.ok && result.entries.size() == 2, "Files with same basename were collapsed");
    const QByteArray beforeRelink = read(store.filePath());
    require(!store.relink(result.entries.front().id, second).ok, "Relink collision accepted");
    require(read(store.filePath()) == beforeRelink, "Failed relocation changed catalogue bytes");
    require(!store.setFavorite(QStringLiteral("unknown-id"), true).ok, "Unknown id accepted");
    require(!store.remove(QStringLiteral("unknown-id")).ok, "Unknown removal accepted");
    require(read(store.filePath()) == beforeRelink, "Unknown-id operations overwrote catalogue");
}

void preserveCorruptAndFutureCatalogue()
{
    QTemporaryDir temporary;
    const auto score = fixture(temporary.path(), QStringLiteral("score.mscx"));
    LocalScoreLibraryStore store(temporary.path() + QStringLiteral("/library.json"));
    const auto good = store.add({ score });
    require(good.ok, "Initial catalogue failed");
    const QByteArray validBytes = read(store.filePath());
    const QJsonObject validRoot = QJsonDocument::fromJson(validBytes).object();
    const auto rejectsWithoutRewriting = [&](const QByteArray& invalid) {
        write(store.filePath(), invalid);
        require(!store.load().ok, "Malformed catalogue loaded without an error");
        require(!store.add({ score }).ok, "Add replaced malformed catalogue");
        require(!store.setFavorite(good.entries.front().id, true).ok, "Favourite replaced malformed catalogue");
        require(!store.remove(good.entries.front().id).ok, "Removal replaced malformed catalogue");
        require(!store.relink(good.entries.front().id, score).ok, "Relink replaced malformed catalogue");
        require(read(store.filePath()) == invalid, "Invalid catalogue bytes were not preserved");
    };
    rejectsWithoutRewriting(QByteArray("{truncated original data"));
    rejectsWithoutRewriting(QByteArray());
    auto root = validRoot;
    root[QStringLiteral("schema_version")] = 3;
    rejectsWithoutRewriting(QJsonDocument(root).toJson());
    root = validRoot;
    root[QStringLiteral("future_property")] = true;
    rejectsWithoutRewriting(QJsonDocument(root).toJson());
    root = validRoot;
    auto entry = root.value(QStringLiteral("entries")).toArray().at(0).toObject();
    entry[QStringLiteral("favorite")] = QStringLiteral("true");
    root[QStringLiteral("entries")] = QJsonArray { entry };
    rejectsWithoutRewriting(QJsonDocument(root).toJson());
    entry[QStringLiteral("favorite")] = false;
    entry[QStringLiteral("id")] = QStringLiteral("not-a-uuid");
    root[QStringLiteral("entries")] = QJsonArray { entry };
    rejectsWithoutRewriting(QJsonDocument(root).toJson());
    entry[QStringLiteral("id")] = good.entries.front().id;
    entry[QStringLiteral("path")] = QStringLiteral("relative.mscx");
    root[QStringLiteral("entries")] = QJsonArray { entry };
    rejectsWithoutRewriting(QJsonDocument(root).toJson());
    root = validRoot;
    entry = root.value(QStringLiteral("entries")).toArray().at(0).toObject();
    auto duplicate = entry;
    duplicate[QStringLiteral("id")] = QUuid::createUuid().toString(QUuid::WithoutBraces);
    root[QStringLiteral("entries")] = QJsonArray { entry, duplicate };
    rejectsWithoutRewriting(QJsonDocument(root).toJson());
    duplicate = entry;
    duplicate[QStringLiteral("path")] = temporary.path() + QStringLiteral("/other.mscx");
    root[QStringLiteral("entries")] = QJsonArray { entry, duplicate };
    rejectsWithoutRewriting(QJsonDocument(root).toJson());
}

void lockAndStaleSnapshots()
{
    QTemporaryDir temporary;
    const auto first = fixture(temporary.path(), QStringLiteral("first.mscx"));
    const auto second = fixture(temporary.path(), QStringLiteral("second.mscx"));
    LocalScoreLibraryStore firstWindow(temporary.path() + QStringLiteral("/library.json"));
    LocalScoreLibraryStore secondWindow(firstWindow.filePath());
    require(secondWindow.load().ok, "Initial second-window read failed");
    const auto initial = firstWindow.add({ first });
    require(initial.ok, "Initial add failed");
    // The second store's old view is deliberately stale. Its mutation must read
    // the first window's committed update instead of overwriting that snapshot.
    auto result = secondWindow.add({ second });
    require(result.ok && result.entries.size() == 2, "Stale second window lost a committed entry");
    require(firstWindow.setFavorite(initial.entries.front().id, true).ok, "Stale favourite mutation failed");
    require(secondWindow.load().entries.size() == 2, "Favourite mutation discarded the other window's add");
    const QByteArray before = read(firstWindow.filePath());
    QLockFile externalLock(firstWindow.filePath() + QStringLiteral(".lock"));
    require(externalLock.tryLock(), "Cannot hold real catalogue lock for test");
    QElapsedTimer elapsed;
    elapsed.start();
    result = secondWindow.add({ second });
    require(!result.ok && !result.error.isEmpty(), "Locked catalogue was overwritten");
    require(elapsed.elapsed() >= 1500 && elapsed.elapsed() < 6000, "Lock wait was not bounded near two seconds");
    require(read(firstWindow.filePath()) == before, "Lock conflict changed the catalogue");
    externalLock.unlock();
    require(secondWindow.load().ok, "Store did not recover after lock release");
}

void writeFailurePreservesData()
{
    QTemporaryDir temporary;
    const auto score = fixture(temporary.path(), QStringLiteral("score.mscx"));
    const QString folder = temporary.path() + QStringLiteral("/catalogue");
    LocalScoreLibraryStore store(folder + QStringLiteral("/nested/library.json"));
    const auto added = store.add({ score });
    require(added.ok, "Initial add failed");
    const QByteArray before = read(store.filePath());
#ifndef Q_OS_WIN
    const auto permissions = QFileInfo(folder).permissions();
    const QString catalogueParent = QFileInfo(store.filePath()).absolutePath();
    const auto catalogueParentPermissions = QFileInfo(catalogueParent).permissions();
    require(QFile::setPermissions(catalogueParent, QFileDevice::ReadOwner | QFileDevice::ExeOwner), "Cannot restrict test folder");
    const auto blocked = store.setFavorite(added.entries.front().id, true);
    require(QFile::setPermissions(catalogueParent, catalogueParentPermissions), "Cannot restore test folder permissions");
    require(!blocked.ok, "Non-writable catalogue folder unexpectedly accepted mutation");
    require(read(store.filePath()) == before, "Permission failure damaged catalogue");
    require(QFile::setPermissions(folder, {}), "Cannot hide test ancestor");
    const auto unreadable = store.load();
    require(QFile::setPermissions(folder, permissions), "Cannot restore hidden ancestor permissions");
    require(!unreadable.ok, "Inaccessible catalogue ancestor was mistaken for an empty library");
    require(read(store.filePath()) == before, "Failed read damaged catalogue");
#endif
    const QString notADirectory = temporary.path() + QStringLiteral("/ordinary-file");
    write(notADirectory, QByteArray("leave this file alone"));
    LocalScoreLibraryStore invalid(notADirectory + QStringLiteral("/library.json"));
    require(!invalid.add({ score }).ok, "Parent ordinary file treated as a directory");
    require(read(notADirectory) == QByteArray("leave this file alone"), "Invalid store location damaged existing file");
}

void concurrentProcesses()
{
    QTemporaryDir temporary;
    const auto first = fixture(temporary.path(), QStringLiteral("process-one.mscx"));
    const auto second = fixture(temporary.path(), QStringLiteral("process-two.mscx"));
    const QString path = temporary.path() + QStringLiteral("/library.json");
    QProcess a;
    QProcess b;
    const QString program = QCoreApplication::applicationFilePath();
    a.start(program, { QStringLiteral("--writer"), path, first.path });
    b.start(program, { QStringLiteral("--writer"), path, second.path });
    require(a.waitForFinished(10000) && b.waitForFinished(10000), "Child writers timed out");
    require(a.exitStatus() == QProcess::NormalExit && a.exitCode() == 0
            && b.exitStatus() == QProcess::NormalExit && b.exitCode() == 0, "Concurrent child writer failed");
    const auto result = LocalScoreLibraryStore(path).load();
    require(result.ok && result.entries.size() == 2, "Concurrent process lost a committed score");
}

void metadataWatchDoesNotBlockAtomicReplacement()
{
    QTemporaryDir temporary;
    require(temporary.isValid(), "Temporary directory unavailable");
    const auto score = fixture(temporary.path(), QString::fromUtf8("Partitions été/Étude.mscx"), QStringLiteral("AAA"));
    const QByteArray scoreBefore = digest(score.path);
    LocalScoreLibraryStore store(temporary.path() + QString::fromUtf8("/Profil été/Bibliothèque.json"));
    const auto added = store.add({ score });
    require(added.ok && added.entries.size() == 1, "Initial watched catalogue failed");
    const QString id = added.entries.front().id;
    const QByteArray catalogueBefore = read(store.filePath());

#ifdef Q_OS_WIN
    // The source of the old race is a real open data reader. Qt's Windows
    // FileRenameInfo replacement cannot replace such a target. Close it before
    // exercising the production metadata-only watcher below.
    QFile oldReader(store.filePath());
    require(oldReader.open(QIODevice::ReadOnly), "Cannot open old-style GUI catalogue reader");
    const auto blocked = store.setFavorite(id, true);
    require(!blocked.ok && blocked.error.startsWith(QStringLiteral("Cannot save the local library")),
            "The Windows data reader did not reproduce the atomic-save conflict");
    require(oldReader.readAll() == catalogueBefore, "Failed atomic save changed the open catalogue");
    oldReader.close();
    require(read(store.filePath()) == catalogueBefore, "Blocked save changed catalogue bytes");
    std::cout << "INFO: Windows old QFile reader reproduced: " << blocked.error.toStdString() << '\n';
#endif

    const QDateTime fixed = QDateTime::fromMSecsSinceEpoch(1700000000000, QTimeZone::UTC);
    const auto restoreTimestamp = [&]() {
        QFile file(store.filePath());
        require(file.open(QIODevice::ReadWrite), "Cannot open test catalogue to restore its timestamp");
        require(file.setFileTime(fixed, QFileDevice::FileModificationTime), "Cannot restore catalogue timestamp");
        file.close();
    };
    restoreTimestamp();
    QString observedStamp = localCatalogMetadataStamp(store.filePath());
    const qint64 baselineSize = QFileInfo(store.filePath()).size();
    QFileSystemWatcher watcher;
    watchLocalCatalog(watcher, store.filePath());
    require(watcher.files().contains(store.filePath()), "Catalogue file watch was not installed");
    int fileEvents = 0;
    int meaningfulDirectoryEvents = 0;
    QObject::connect(&watcher, &QFileSystemWatcher::fileChanged, &watcher, [&](const QString& path) {
        require(path == store.filePath(), "Unexpected watched file");
        ++fileEvents;
        observedStamp = localCatalogMetadataStamp(store.filePath());
        watchLocalCatalog(watcher, store.filePath());
    });
    QObject::connect(&watcher, &QFileSystemWatcher::directoryChanged, &watcher, [&]() {
        const QString current = localCatalogMetadataStamp(store.filePath());
        if (current != observedStamp) {
            ++meaningfulDirectoryEvents;
            observedStamp = current;
            watchLocalCatalog(watcher, store.filePath());
        }
    });
    const auto drainEvents = [&]() {
        QElapsedTimer interval;
        interval.start();
        while (interval.elapsed() < 200) {
            QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
            QThread::msleep(5);
        }
    };
    drainEvents();
    const auto waitForReplacement = [&](int before) {
        QElapsedTimer timeout;
        timeout.start();
        while (fileEvents + meaningfulDirectoryEvents <= before && timeout.elapsed() < 5000) {
            QCoreApplication::processEvents(QEventLoop::AllEvents, 50);
            QThread::msleep(5);
        }
        require(fileEvents + meaningfulDirectoryEvents > before,
                "Native watcher missed an equal-size/equal-timestamp atomic replacement");
        require(watcher.files().contains(store.filePath()), "File watch was not rearmed after atomic replacement");
        drainEvents();
    };
    for (const QString& title : { QStringLiteral("BBB"), QStringLiteral("CCC") }) {
        auto replacement = score;
        replacement.title = title;
        const int before = fileEvents + meaningfulDirectoryEvents;
        // Metadata checks may be held as values across the mutation; they own
        // no catalogue stream and cannot block QSaveFile's target replacement.
        const QString observed = localCatalogMetadataStamp(store.filePath());
#ifdef Q_OS_WIN
        const QString identity = localCatalogWindowsIdentity(QFileInfo(store.filePath()));
        require(!identity.isEmpty(), "The Windows runner filesystem did not provide a catalogue entry identity");
#endif
        const auto changed = store.relink(id, replacement);
        require(changed.ok && changed.entries.front().title == title, "Metadata-only watcher blocked atomic commit");
        restoreTimestamp();
        require(QFileInfo(store.filePath()).size() == baselineSize
                && QFileInfo(store.filePath()).lastModified().toMSecsSinceEpoch() == fixed.toMSecsSinceEpoch(),
                "Equal-size/equal-timestamp replacement test precondition failed");
#ifdef Q_OS_WIN
        require(localCatalogWindowsIdentity(QFileInfo(store.filePath())) != identity
                && localCatalogMetadataStamp(store.filePath()) != observed,
                "A Windows atomic replacement with equal metadata must change the catalogue entry identity");
#else
        require(localCatalogMetadataStamp(store.filePath()) == observed,
                "The native file-notification test must retain equal metadata on this host");
#endif
        waitForReplacement(before);
        const auto reopened = store.load();
        require(reopened.ok && reopened.entries.front().title == title, "Reopening lost the committed watched metadata");
    }
    const int beforeRead = fileEvents;
    const int meaningfulBeforeRead = meaningfulDirectoryEvents;
    require(store.load().ok, "Locked read after replacement failed");
    drainEvents();
    require(fileEvents == beforeRead && meaningfulDirectoryEvents == meaningfulBeforeRead,
            "Read-lock-only directory activity triggered a meaningful catalogue change");
    const int beforeFavorite = fileEvents + meaningfulDirectoryEvents;
    const auto favorite = store.setFavorite(id, true);
    require(favorite.ok && favorite.entries.front().favorite, "Favorite commit failed without a data reader");
    waitForReplacement(beforeFavorite);
    require(digest(score.path) == scoreBefore, "Catalogue watch/save operations changed the score");
    require(localCatalogMetadataStamp(temporary.path() + QStringLiteral("/missing.json")) == QStringLiteral("missing"),
            "Missing catalogue metadata was not represented without creating a file");
}

void explicitCollectionMigration()
{
    QTemporaryDir temporary;
    const auto score = fixture(temporary.path(), QString::fromUtf8("Été.mscx"));
    const auto originalScore = digest(score.path);
    LocalScoreLibraryStore store(temporary.path() + QStringLiteral("/library.json"));
    require(store.load().schemaVersion == 1, "A fresh catalogue implicitly enabled collections");
    const auto added = store.add({ score });
    require(added.ok && added.schemaVersion == 1, "Adding a score changed the catalogue version");
    const QString id = added.entries.front().id;
    const auto favored = store.setFavorite(id, true);
    require(favored.ok && favored.schemaVersion == 1, "Favourite implicitly enabled collections");
    const auto before = read(store.filePath());
    require(!store.createCollection(QStringLiteral("Concert")).ok, "Collection creation implicitly migrated v1");
    require(read(store.filePath()) == before, "Refused creation rewrote the v1 catalogue");
    const auto enabled = store.enableCollections();
    require(enabled.ok && enabled.schemaVersion == 2 && enabled.collections.isEmpty()
            && enabled.entries.size() == 1 && enabled.entries.front().id == id
            && enabled.entries.front().path == score.path && enabled.entries.front().favorite
            && enabled.entries.front().title == score.title && enabled.entries.front().composer == score.composer,
            "Explicit migration lost score identity, metadata, favourite or path");
    const auto migrated = read(store.filePath());
    require(store.enableCollections().ok && read(store.filePath()) == migrated, "Enabling collections twice was not idempotent");
    const auto reopened = LocalScoreLibraryStore(store.filePath()).load();
    require(reopened.ok && reopened.schemaVersion == 2 && reopened.entries.front().favorite,
            "A reopened v2 catalogue lost its version or favourite");
    require(digest(score.path) == originalScore, "Migration changed the score file");
}

void collectionNamesMembershipAndOrder()
{
    QTemporaryDir temporary;
    const auto a = fixture(temporary.path(), QStringLiteral("a.mscx"));
    const auto b = fixture(temporary.path(), QStringLiteral("b.mscx"));
    const auto c = fixture(temporary.path(), QStringLiteral("c.mscx"));
    const auto replacement = fixture(temporary.path(), QStringLiteral("moved/b.mscx"));
    const QList<QByteArray> originals { digest(a.path), digest(b.path), digest(c.path), digest(replacement.path) };
    LocalScoreLibraryStore store(temporary.path() + QStringLiteral("/library.json"));
    const auto added = store.add({ a, b, c });
    require(added.ok && store.enableCollections().ok, "Could not prepare collection fixture");
    const QString aId = added.entries[0].id, bId = added.entries[1].id, cId = added.entries[2].id;
    auto result = store.createCollection(QString::fromUtf8("  Été — 東京  "));
    require(result.ok && result.collections.size() == 1 && result.collections[0].name == QString::fromUtf8("Été — 東京"),
            "Collection name was not normalized or preserved as Unicode");
    const QString firstId = result.collections[0].id;
    require(!QUuid(firstId).isNull(), "Collection needs a stable UUID");
    const auto beforeDuplicate = read(store.filePath());
    require(!store.createCollection(QString::fromUtf8("ETE — 東京")).ok
            && read(store.filePath()) == beforeDuplicate, "Case/diacritic duplicate collection was accepted");
    for (const QString& invalid : { QString(), QStringLiteral("   "), QString(81, QLatin1Char('a')),
                                   QStringLiteral("Line\nbreak"), QStringLiteral("Tab\tname") }) {
        require(!store.createCollection(invalid).ok && read(store.filePath()) == beforeDuplicate,
                "Invalid collection name changed the catalogue");
    }
    result = store.createCollection(QStringLiteral("Second"));
    require(result.ok && result.collections.size() == 2, "Second collection failed");
    const QString secondId = result.collections[1].id;
    require(store.renameCollection(firstId, QStringLiteral(" Concert ")).ok, "Collection rename failed");
    require(!store.renameCollection(secondId, QStringLiteral("CONCERT")).ok, "Rename accepted a duplicate name");
    require(store.setCollectionEntry(firstId, aId, true).ok && store.setCollectionEntry(firstId, bId, true).ok
            && store.setCollectionEntry(firstId, cId, true).ok, "Adding collection membership failed");
    auto memberships = store.setCollectionEntry(firstId, bId, true);
    require(memberships.ok && memberships.collections[0].entryIds == QStringList({ aId, bId, cId }),
            "Duplicate membership changed order or duplicated a score");
    result = store.moveCollectionEntry(firstId, cId, -1);
    require(result.ok && result.collections[0].entryIds == QStringList({ aId, cId, bId }), "Move up lost manual list order");
    result = store.moveCollectionEntry(firstId, aId, 1);
    require(result.ok && result.collections[0].entryIds == QStringList({ cId, aId, bId }), "Move down failed");
    require(store.moveCollectionEntry(firstId, cId, -1).ok && store.moveCollectionEntry(firstId, bId, 1).ok,
            "Moving at the list boundary should be a safe no-op");
    const auto beforeBadMove = read(store.filePath());
    require(!store.moveCollectionEntry(firstId, aId, 2).ok && read(store.filePath()) == beforeBadMove,
            "An invalid move changed the collection");
    require(!store.setCollectionEntry(firstId, QStringLiteral("missing-score"), true).ok
            && !store.setCollectionEntry(QStringLiteral("missing-collection"), aId, true).ok
            && !store.renameCollection(QStringLiteral("missing-collection"), QStringLiteral("Rename")).ok
            && !store.removeCollection(QStringLiteral("missing-collection")).ok
            && read(store.filePath()) == beforeBadMove, "Unknown membership/collection mutation changed the catalogue");
    require(store.setCollectionEntry(secondId, bId, true).ok && store.setFavorite(bId, true).ok,
            "Favourite or second collection lost membership");
    result = store.relink(bId, replacement);
    require(result.ok && result.collections[0].entryIds == QStringList({ cId, aId, bId })
            && result.collections[1].entryIds == QStringList({ bId }) && result.entries[1].id == bId
            && result.entries[1].favorite && result.entries[1].path == replacement.path, "Relink broke collection references");
    result = store.setCollectionEntry(firstId, aId, false);
    require(result.ok && result.collections[0].entryIds == QStringList({ cId, bId }), "Removing membership changed another score");
    result = store.remove(bId);
    require(result.ok && result.collections[0].entryIds == QStringList({ cId }) && result.collections[1].entryIds.isEmpty()
            && result.entries.size() == 2, "Removing a score left dangling collection references");
    result = store.removeCollection(firstId);
    require(result.ok && result.collections.size() == 1 && result.collections[0].id == secondId && result.entries.size() == 2,
            "Removing collection deleted library entries");
    require(digest(a.path) == originals[0] && digest(b.path) == originals[1]
            && digest(c.path) == originals[2] && digest(replacement.path) == originals[3],
            "Collection operations changed or deleted a score file");
}

void corruptCollectionsRemainUntouched()
{
    QTemporaryDir temporary;
    const auto score = fixture(temporary.path(), QStringLiteral("score.mscx"));
    LocalScoreLibraryStore store(temporary.path() + QStringLiteral("/library.json"));
    const auto added = store.add({ score });
    require(added.ok && store.enableCollections().ok, "Could not prepare v2 corruption fixture");
    const auto created = store.createCollection(QStringLiteral("Concert"));
    require(created.ok, "Could not create v2 corruption fixture collection");
    const QString collectionId = created.collections.front().id, scoreId = added.entries.front().id;
    const auto valid = QJsonDocument::fromJson(read(store.filePath())).object();
    const auto reject = [&](const QJsonObject& malformed) {
        const QByteArray bytes = QJsonDocument(malformed).toJson();
        write(store.filePath(), bytes);
        require(!store.load().ok && !store.enableCollections().ok && !store.createCollection(QStringLiteral("Next")).ok
                && !store.renameCollection(collectionId, QStringLiteral("Next")).ok && !store.removeCollection(collectionId).ok
                && !store.setCollectionEntry(collectionId, scoreId, true).ok
                && !store.moveCollectionEntry(collectionId, scoreId, 1).ok
                && !store.setFavorite(scoreId, true).ok && !store.remove(scoreId).ok
                && read(store.filePath()) == bytes, "Malformed collections were silently repaired or rewritten");
    };
    auto root = valid;
    root[QStringLiteral("schema_version")] = 3;
    reject(root);
    root = valid;
    root.remove(QStringLiteral("collections"));
    reject(root);
    root = valid;
    root[QStringLiteral("collections")] = QStringLiteral("not-an-array");
    reject(root);
    root = valid;
    auto collection = valid.value(QStringLiteral("collections")).toArray()[0].toObject();
    collection[QStringLiteral("entry_ids")] = QJsonArray { QStringLiteral("missing-score") };
    root[QStringLiteral("collections")] = QJsonArray { collection };
    reject(root);
    collection[QStringLiteral("entry_ids")] = QJsonArray { scoreId, scoreId };
    root[QStringLiteral("collections")] = QJsonArray { collection };
    reject(root);
    collection[QStringLiteral("entry_ids")] = QJsonArray { 7 };
    root[QStringLiteral("collections")] = QJsonArray { collection };
    reject(root);
    collection[QStringLiteral("entry_ids")] = QJsonArray {};
    collection[QStringLiteral("id")] = QStringLiteral("not-a-uuid");
    root[QStringLiteral("collections")] = QJsonArray { collection };
    reject(root);
    collection[QStringLiteral("id")] = collectionId;
    collection[QStringLiteral("name")] = QStringLiteral("   ");
    root[QStringLiteral("collections")] = QJsonArray { collection };
    reject(root);
    collection[QStringLiteral("name")] = QStringLiteral("Concert");
    auto duplicate = collection;
    duplicate[QStringLiteral("id")] = QUuid::createUuid().toString(QUuid::WithoutBraces);
    duplicate[QStringLiteral("name")] = QStringLiteral("CONCERT");
    root[QStringLiteral("collections")] = QJsonArray { collection, duplicate };
    reject(root);
    duplicate[QStringLiteral("name")] = QStringLiteral("Other");
    duplicate[QStringLiteral("id")] = collectionId;
    root[QStringLiteral("collections")] = QJsonArray { collection, duplicate };
    reject(root);
    root = valid;
    root[QStringLiteral("extra")] = true;
    reject(root);
}

void concurrentCollectionMembers()
{
    QTemporaryDir temporary;
    const auto first = fixture(temporary.path(), QStringLiteral("first.mscx"));
    const auto second = fixture(temporary.path(), QStringLiteral("second.mscx"));
    LocalScoreLibraryStore windowA(temporary.path() + QStringLiteral("/library.json"));
    const auto added = windowA.add({ first, second });
    require(added.ok && windowA.enableCollections().ok, "Could not prepare concurrent collection fixture");
    const auto created = windowA.createCollection(QStringLiteral("Concert"));
    require(created.ok, "Could not create concurrent collection fixture");
    const QString collectionId = created.collections[0].id;
    LocalScoreLibraryStore staleWindow(windowA.filePath());
    require(staleWindow.load().ok, "Initial stale-window collection read failed");
    QProcess a, b;
    const QString program = QCoreApplication::applicationFilePath();
    a.start(program, { QStringLiteral("--collection-writer"), windowA.filePath(), collectionId, added.entries[0].id });
    b.start(program, { QStringLiteral("--collection-writer"), windowA.filePath(), collectionId, added.entries[1].id });
    require(a.waitForFinished(10000) && b.waitForFinished(10000), "Concurrent collection writers timed out");
    require(a.exitStatus() == QProcess::NormalExit && a.exitCode() == 0 && b.exitStatus() == QProcess::NormalExit && b.exitCode() == 0,
            "Concurrent collection child writer failed");
    auto result = staleWindow.setFavorite(added.entries[0].id, true);
    require(result.ok && result.entries[0].favorite && result.collections[0].entryIds.size() == 2
            && result.collections[0].entryIds.contains(added.entries[0].id) && result.collections[0].entryIds.contains(added.entries[1].id),
            "Stale favourite mutation lost a concurrently committed member");
    result = windowA.renameCollection(collectionId, QStringLiteral("Rehearsal"));
    require(result.ok && result.collections[0].entryIds.size() == 2 && result.entries[0].favorite,
            "Stale rename overwrote memberships or favourite");
}

void nativeXmlStructuralGate()
{
    const QList<QByteArray> invalid {
        {},
        QByteArray("  \n\t "),
        QByteArray("not a score"),
        QByteArray("{\"title\":\"score\"}"),
        QByteArray("<other version=\"4.40\"><Score/></other>"),
        QByteArray("<museScore><Score/></museScore>"),
        QByteArray("<museScore version=\" \" ><Score/></museScore>"),
        QByteArray("<museScore version=\"4.40\"/>"),
        QByteArray("<museScore version=\"4.40\"><Score/>"),
        QByteArray("<museScore version=\"4.40\"><Score/></museScore>trailing text"),
        QByteArray("<museScore version=\"4.40\"><Score><Staff></Score></museScore>"),
        QByteArray("<museScore version=\"4.40\"><Staff/></museScore>"),
        QByteArray("<museScore version=\"4.40\"><wrapper><Score/></wrapper></museScore>"),
        QByteArray("<!DOCTYPE museScore><museScore version=\"4.40\"><Score/></museScore>"),
        QByteArray("<!DOCTYPE museScore [<!ENTITY title \"Injected\">]><museScore version=\"4.40\"><Score>&title;</Score></museScore>")
    };
    for (const auto& bytes : invalid) {
        require(!isNativeScoreXml(bytes), "Invalid or DTD-based native score XML accepted");
    }
    require(isNativeScoreXml(QByteArray("<?xml version=\"1.0\"?><museScore version=\"4.40\"><Score><Staff id=\"1\"/></Score></museScore>")),
            "Modern native score shape refused");
    require(isNativeScoreXml(QByteArray("<museScore version=\"1.14\"><Staff id=\"1\"><Measure/></Staff></museScore>")),
            "Legacy native score shape refused");
    require(isNativeScoreXml(QString::fromUtf8("<museScore version=\"4.40\"><Score><metaTag name=\"workTitle\">Étude été — 東京</metaTag></Score></museScore>").toUtf8()),
            "Non-ASCII native score text refused");
}
}

int main(int argc, char** argv)
{
    QCoreApplication application(argc, argv);
    if (application.arguments().size() == 4 && application.arguments()[1] == QStringLiteral("--writer")) {
        LocalScoreLibraryStore store(application.arguments()[2]);
        const auto result = store.add({ { {}, application.arguments()[3], QStringLiteral("Writer"), {}, false } });
        return result.ok ? 0 : 1;
    }
    if (application.arguments().size() == 5 && application.arguments()[1] == QStringLiteral("--collection-writer")) {
        LocalScoreLibraryStore store(application.arguments()[2]);
        return store.setCollectionEntry(application.arguments()[3], application.arguments()[4], true).ok ? 0 : 1;
    }
    const QList<QPair<const char*, std::function<void()>>> tests {
        { "persistence, Unicode, stable id, deduplication and no score mutation", persistAndDeduplicate },
        { "missing score retained and relink preserves id/favourite", retainAndRelinkMissing },
        { "all-or-nothing add, equal basenames and relocation collisions", rejectInvalidBatchAndCollision },
        { "corrupt, future and duplicate catalogues preserved", preserveCorruptAndFutureCatalogue },
        { "bounded real lock conflict and stale-window merge", lockAndStaleSnapshots },
        { "permission and invalid-parent failures preserve data", writeFailurePreservesData },
        { "concurrent real processes preserve both writes", concurrentProcesses },
        { "metadata/identity watch permits atomic saves, equal-time replacements and native rearming", metadataWatchDoesNotBlockAtomicReplacement },
        { "explicit v1 to v2 collections migration preserves metadata and never happens during ordinary writes", explicitCollectionMigration },
        { "collection CRUD, Unicode names, membership order, relink and removal preserve score files", collectionNamesMembershipAndOrder },
        { "invalid/future collection structures and foreign references preserve exact catalogue bytes", corruptCollectionsRemainUntouched },
        { "concurrent real membership writers and stale windows preserve all committed changes", concurrentCollectionMembers },
        { "native XML gate rejects malformed/non-native/DTD and accepts modern/legacy Unicode", nativeXmlStructuralGate }
    };
    int failures = 0;
    for (const auto& test : tests) {
        try {
            test.second();
            std::cout << "PASS: " << test.first << '\n';
        } catch (const std::exception& error) {
            ++failures;
            std::cerr << "FAIL: " << test.first << ": " << error.what() << '\n';
        }
    }
    std::cout << tests.size() - failures << '/' << tests.size() << " production-store runtime scenarios passed (Qt " << qVersion() << ").\n";
    return failures ? 1 : 0;
}
