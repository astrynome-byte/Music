// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#include "localscorelibrarystore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QLockFile>
#include <QSaveFile>
#include <QSet>
#include <QUuid>

#include <algorithm>
#include <utility>

namespace mu::project {
namespace {
constexpr int LOCK_TIMEOUT_MS = 2000;

LocalLibraryResult failure(const QString& error)
{
    return { false, error, {} };
}

QString absolutePath(const QString& path)
{
    return QDir::cleanPath(QFileInfo(path).absoluteFilePath());
}

QString pathKey(const QString& path)
{
    const QFileInfo file(path);
    QString key = file.canonicalFilePath();
    if (key.isEmpty()) {
        key = absolutePath(path);
    }
#ifdef Q_OS_WIN
    key = key.toCaseFolded();
#endif
    return key;
}

bool isNativePath(const QString& path)
{
    const QString suffix = QFileInfo(path).suffix().toLower();
    return suffix == QStringLiteral("mscz") || suffix == QStringLiteral("mscx");
}

bool validateSelectedFile(const QString& path, const QString& cataloguePath, QString& error)
{
    if (path.isEmpty() || !QFileInfo(path).isAbsolute() || !isNativePath(path)) {
        error = QStringLiteral("Choose an existing MSCZ or MSCX score using an absolute path.");
        return false;
    }
    if (pathKey(path) == pathKey(cataloguePath)) {
        error = QStringLiteral("The library catalogue cannot also be a score entry.");
        return false;
    }
    QFile file(path);
    if (!QFileInfo(path).isFile() || !file.open(QIODevice::ReadOnly)) {
        error = QStringLiteral("The selected score is missing or unreadable: %1").arg(path);
        return false;
    }
    return true;
}

QByteArray serialize(const QList<LocalLibraryEntry>& entries)
{
    QJsonArray array;
    for (const LocalLibraryEntry& entry : entries) {
        array.append(QJsonObject {
            { QStringLiteral("id"), entry.id },
            { QStringLiteral("path"), entry.path },
            { QStringLiteral("title"), entry.title },
            { QStringLiteral("composer"), entry.composer },
            { QStringLiteral("favorite"), entry.favorite }
        });
    }
    return QJsonDocument(QJsonObject {
        { QStringLiteral("schema_version"), 1 },
        { QStringLiteral("entries"), array }
    }).toJson(QJsonDocument::Indented);
}

QString lockError(const QLockFile& lock)
{
    if (lock.error() == QLockFile::LockFailedError) {
        return QStringLiteral("The local library is busy in another window. Try again.");
    }
    return QStringLiteral("Cannot lock the local library. Check the catalogue folder permissions.");
}
}

LocalScoreLibraryStore::LocalScoreLibraryStore(QString filePath)
    : m_filePath(absolutePath(std::move(filePath)))
{
}

QString LocalScoreLibraryStore::filePath() const
{
    return m_filePath;
}

LocalLibraryResult LocalScoreLibraryStore::readUnlocked() const
{
    const QFileInfo info(m_filePath);
    // Absence is an empty new catalogue; unreadable/corrupt data is not absence.
    if (!info.exists() && !info.isSymLink()) {
        return { true, {}, {} };
    }
    QFile file(m_filePath);
    if (!info.isFile() || !file.open(QIODevice::ReadOnly)) {
        return failure(QStringLiteral("Cannot read the local library catalogue: %1").arg(file.errorString()));
    }
    const QByteArray bytes = file.readAll();
    if (file.error() != QFileDevice::NoError) {
        return failure(QStringLiteral("Reading the local library failed: %1").arg(file.errorString()));
    }
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(bytes, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        return failure(QStringLiteral("The local library catalogue is invalid; it was left unchanged. %1")
                       .arg(parseError.errorString()));
    }
    const QJsonObject root = document.object();
    if (root.size() != 2 || !root.value(QStringLiteral("schema_version")).isDouble()
        || root.value(QStringLiteral("schema_version")).toDouble() != 1.0
        || !root.value(QStringLiteral("entries")).isArray()) {
        return failure(QStringLiteral("Unsupported or invalid local library schema; the catalogue was left unchanged."));
    }
    QList<LocalLibraryEntry> entries;
    QSet<QString> ids;
    QSet<QString> paths;
    for (const QJsonValue& value : root.value(QStringLiteral("entries")).toArray()) {
        if (!value.isObject()) {
            return failure(QStringLiteral("Invalid local library entry; the catalogue was left unchanged."));
        }
        const QJsonObject object = value.toObject();
        if (object.size() != 5 || !object.value(QStringLiteral("id")).isString()
            || !object.value(QStringLiteral("path")).isString() || !object.value(QStringLiteral("title")).isString()
            || !object.value(QStringLiteral("composer")).isString() || !object.value(QStringLiteral("favorite")).isBool()) {
            return failure(QStringLiteral("Invalid local library entry fields; the catalogue was left unchanged."));
        }
        LocalLibraryEntry entry { object.value(QStringLiteral("id")).toString(),
                                  object.value(QStringLiteral("path")).toString(),
                                  object.value(QStringLiteral("title")).toString(),
                                  object.value(QStringLiteral("composer")).toString(),
                                  object.value(QStringLiteral("favorite")).toBool() };
        const QUuid id(entry.id);
        const QString idKey = id.toString(QUuid::WithoutBraces);
        const QString key = pathKey(entry.path);
        if (id.isNull() || entry.path.isEmpty() || !QFileInfo(entry.path).isAbsolute() || !isNativePath(entry.path)
            || key == pathKey(m_filePath) || ids.contains(idKey) || paths.contains(key)) {
            return failure(QStringLiteral("Duplicate or invalid local library identifiers/paths; the catalogue was left unchanged."));
        }
        ids.insert(idKey);
        paths.insert(key);
        entries.append(std::move(entry));
    }
    return { true, {}, entries };
}

LocalLibraryResult LocalScoreLibraryStore::load() const
{
    // Checking exists() alone would mistake an inaccessible ancestor for a new
    // empty catalogue. Creating/accessing only our own profile folder lets that
    // error surface before the locked read; score folders are never created.
    if (!QDir().mkpath(QFileInfo(m_filePath).absolutePath())) {
        return failure(QStringLiteral("Cannot access or create the local library folder."));
    }
    QLockFile lock(m_filePath + QStringLiteral(".lock"));
    if (!lock.tryLock(LOCK_TIMEOUT_MS)) {
        return failure(lockError(lock));
    }
    return readUnlocked();
}

LocalLibraryResult LocalScoreLibraryStore::mutate(const Mutation& mutation)
{
    if (!QDir().mkpath(QFileInfo(m_filePath).absolutePath())) {
        return failure(QStringLiteral("Cannot create the local library folder."));
    }
    QLockFile lock(m_filePath + QStringLiteral(".lock"));
    if (!lock.tryLock(LOCK_TIMEOUT_MS)) {
        return failure(lockError(lock));
    }
    LocalLibraryResult result = readUnlocked();
    if (!result.ok) {
        return result;
    }
    QString error;
    if (!mutation(result.entries, error)) {
        return failure(error);
    }
    // Never fall back to in-place truncation if atomic replacement is denied.
    QSaveFile file(m_filePath);
    file.setDirectWriteFallback(false);
    const QByteArray bytes = serialize(result.entries);
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
        file.cancelWriting();
        return failure(QStringLiteral("Cannot save the local library; the previous catalogue was preserved. %1")
                       .arg(file.errorString()));
    }
    return result;
}

LocalLibraryResult LocalScoreLibraryStore::add(const QList<LocalLibraryEntry>& additions)
{
    return mutate([this, additions](QList<LocalLibraryEntry>& entries, QString& error) {
        for (const LocalLibraryEntry& candidate : additions) {
            if (!validateSelectedFile(candidate.path, m_filePath, error)) {
                return false;
            }
            const QString key = pathKey(candidate.path);
            if (std::any_of(entries.cbegin(), entries.cend(), [&key](const LocalLibraryEntry& entry) {
                return pathKey(entry.path) == key;
            })) {
                continue; // Keep the existing stable id, favourite and metadata.
            }
            LocalLibraryEntry entry = candidate;
            entry.path = absolutePath(entry.path);
            entry.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
            entries.append(std::move(entry));
        }
        return true;
    });
}

LocalLibraryResult LocalScoreLibraryStore::setFavorite(const QString& id, bool favorite)
{
    return mutate([&id, favorite](QList<LocalLibraryEntry>& entries, QString& error) {
        for (LocalLibraryEntry& entry : entries) {
            if (entry.id == id) {
                entry.favorite = favorite;
                return true;
            }
        }
        error = QStringLiteral("The library entry no longer exists. Refresh the library.");
        return false;
    });
}

LocalLibraryResult LocalScoreLibraryStore::remove(const QString& id)
{
    return mutate([&id](QList<LocalLibraryEntry>& entries, QString& error) {
        for (auto it = entries.begin(); it != entries.end(); ++it) {
            if (it->id == id) {
                entries.erase(it); // Only the catalogue entry is removed.
                return true;
            }
        }
        error = QStringLiteral("The library entry no longer exists. Refresh the library.");
        return false;
    });
}

LocalLibraryResult LocalScoreLibraryStore::relink(const QString& id, const LocalLibraryEntry& replacement)
{
    return mutate([this, &id, &replacement](QList<LocalLibraryEntry>& entries, QString& error) {
        if (!validateSelectedFile(replacement.path, m_filePath, error)) {
            return false;
        }
        const QString key = pathKey(replacement.path);
        for (const LocalLibraryEntry& entry : entries) {
            if (entry.id != id && pathKey(entry.path) == key) {
                error = QStringLiteral("That score is already registered in the local library.");
                return false;
            }
        }
        for (LocalLibraryEntry& entry : entries) {
            if (entry.id == id) {
                entry.path = absolutePath(replacement.path);
                entry.title = replacement.title;
                entry.composer = replacement.composer;
                return true; // Stable id and favourite survive relocation.
            }
        }
        error = QStringLiteral("The library entry no longer exists. Refresh the library.");
        return false;
    });
}
}
