// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#include "localscorelibrarystore.h"
#include "localcatalogsnapshot.h"
#include "localscorexmlcheck.h"

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLockFile>
#include <QProcess>
#include <QTemporaryDir>
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
    root[QStringLiteral("schema_version")] = 2;
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

void snapshotDoesNotBlockAtomicReplacement()
{
    QTemporaryDir temporary;
    require(temporary.isValid(), "Temporary directory unavailable");
    const auto score = fixture(temporary.path(), QString::fromUtf8("Partitions été/Étude.mscx"));
    const QByteArray scoreBefore = digest(score.path);
    LocalScoreLibraryStore store(temporary.path() + QString::fromUtf8("/Profil été/Bibliothèque.json"));
    const auto added = store.add({ score });
    require(added.ok && added.entries.size() == 1, "Initial snapshot catalogue failed");
    const QString id = added.entries.front().id;
    const QByteArray catalogueBefore = read(store.filePath());

#ifdef Q_OS_WIN
    // Reproduce the old GUI hash-reader race deterministically: hold its
    // ordinary QFile open across the real store commit. No timing/retry loop.
    QFile oldReader(store.filePath());
    require(oldReader.open(QIODevice::ReadOnly), "Cannot open old-style snapshot reader");
    const auto blocked = store.setFavorite(id, true);
    require(!blocked.ok && blocked.error.startsWith(QStringLiteral("Cannot save the local library")),
            "The Windows no-DELETE reader did not reproduce the atomic-save conflict");
    require(oldReader.readAll() == catalogueBefore, "A failed atomic save changed the open snapshot");
    oldReader.close();
    require(read(store.filePath()) == catalogueBefore, "A blocked save changed catalogue bytes");
    std::cout << "INFO: Windows old QFile reader reproduced: " << blocked.error.toStdString() << '\n';
#endif

    // Keep the exact production reader open while the writer replaces its
    // catalogue. The old handle must remain a coherent snapshot; a fresh read
    // must see the newly committed favourite. This also covers another window.
    QFile snapshot;
    require(openLocalLibrarySnapshot(snapshot, store.filePath()), "Cannot open production catalogue snapshot");
    require(snapshot.isReadable() && !snapshot.isWritable(), "Snapshot reader must remain read-only");
    const auto changed = store.setFavorite(id, true);
    require(changed.ok && changed.entries.front().favorite, "Snapshot reader blocked atomic favourite commit");
    require(snapshot.readAll() == catalogueBefore, "An open snapshot mixed the old and new catalogues");
    require(snapshot.error() == QFileDevice::NoError, "Reading the open snapshot failed after replacement");
    snapshot.close();
    const auto reopened = LocalScoreLibraryStore(store.filePath()).load();
    require(reopened.ok && reopened.entries.size() == 1 && reopened.entries.front().id == id
            && reopened.entries.front().favorite, "Fresh catalogue read lost the committed favourite");
    QFile fresh;
    require(openLocalLibrarySnapshot(fresh, store.filePath()), "Cannot reopen catalogue snapshot after replacement");
    require(fresh.readAll() == read(store.filePath()) && fresh.error() == QFileDevice::NoError,
            "Fresh snapshot did not see the committed catalogue");
    fresh.close();
    QFile missing;
    const QString missingPath = temporary.path() + QStringLiteral("/missing.json");
    require(!openLocalLibrarySnapshot(missing, missingPath) && !QFileInfo::exists(missingPath),
            "Snapshot read created a missing catalogue");
    require(digest(score.path) == scoreBefore, "Snapshot/save operations changed the score");
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
    const QList<QPair<const char*, std::function<void()>>> tests {
        { "persistence, Unicode, stable id, deduplication and no score mutation", persistAndDeduplicate },
        { "missing score retained and relink preserves id/favourite", retainAndRelinkMissing },
        { "all-or-nothing add, equal basenames and relocation collisions", rejectInvalidBatchAndCollision },
        { "corrupt, future and duplicate catalogues preserved", preserveCorruptAndFutureCatalogue },
        { "bounded real lock conflict and stale-window merge", lockAndStaleSnapshots },
        { "permission and invalid-parent failures preserve data", writeFailurePreservesData },
        { "concurrent real processes preserve both writes", concurrentProcesses },
        { "open catalogue snapshots allow atomic replacement and preserve old/new views", snapshotDoesNotBlockAtomicReplacement },
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
