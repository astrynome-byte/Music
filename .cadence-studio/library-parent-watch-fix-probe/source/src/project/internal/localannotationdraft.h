// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include "localscorelibrarystore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLockFile>
#include <QSaveFile>
#include <QUuid>

#include <memory>

namespace mu::project {
struct LocalAnnotationDraft {
    LocalLibraryAnnotation note;
    QString sourcePath;
    QString entryTitle {};
    QString scorePath {};
};

// Recovery journals are separate from the catalogue and score files. Each panel
// owns a unique journal and lifetime lock; another live panel cannot restore or
// delete it. A failed catalogue commit leaves this recovery copy untouched.
class LocalAnnotationDraftJournal
{
public:
    explicit LocalAnnotationDraftJournal(const QString& cataloguePath)
        : m_folder(QFileInfo(cataloguePath).absolutePath() + QStringLiteral("/annotation_drafts")),
          m_path(m_folder + QLatin1Char('/') + QUuid::createUuid().toString(QUuid::WithoutBraces) + QStringLiteral(".json")) {}

    bool save(const LocalLibraryAnnotation& note, QString& error, const QString& entryTitle = {}, const QString& scorePath = {})
    {
        if (QUuid(note.entryId).isNull() || (!note.id.isEmpty() && QUuid(note.id).isNull())
            || note.text.size() > 8000 || note.revision < 0 || note.measure < 0 || note.measure > 999999
            || note.page < 0 || note.page > 999999) {
            error = QStringLiteral("Cannot preserve the private-note draft: invalid fields.");
            return false;
        }
        if (!QDir().mkpath(m_folder)) {
            error = QStringLiteral("Cannot preserve the private-note draft: folder unavailable.");
            return false;
        }
        if (!m_owner) {
            auto owner = std::make_unique<QLockFile>(m_path + QStringLiteral(".owner.lock"));
            if (!owner->tryLock(0)) {
                error = QStringLiteral("Cannot preserve the private-note draft: journal busy.");
                return false;
            }
            m_owner = std::move(owner);
        }
        QJsonObject object {
            { QStringLiteral("schema_version"), 2 }, { QStringLiteral("entry_id"), note.entryId },
            { QStringLiteral("id"), note.id }, { QStringLiteral("revision"), note.revision },
            { QStringLiteral("text"), note.text }, { QStringLiteral("measure"), note.measure },
            { QStringLiteral("page"), note.page },
            { QStringLiteral("entry_title"), entryTitle.left(512) }, { QStringLiteral("score_path"), scorePath.left(4096) }
        };
        const auto bytes = QJsonDocument(object).toJson(QJsonDocument::Indented);
        QSaveFile file(m_path);
        file.setDirectWriteFallback(false);
        if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
            file.cancelWriting();
            error = QStringLiteral("Cannot preserve the private-note draft: %1").arg(file.errorString());
            return false;
        }
        return true;
    }

    bool clear(QString& error)
    {
        if (QFileInfo::exists(m_path) && !QFile::remove(m_path)) {
            error = QStringLiteral("Cannot remove the private-note recovery draft.");
            return false;
        }
        return true;
    }

    QList<LocalAnnotationDraft> recoverable(const QString& entryId = {}) const
    {
        QList<LocalAnnotationDraft> drafts;
        const QDir directory(m_folder);
        for (const auto& info : directory.entryInfoList({ QStringLiteral("*.json") }, QDir::Files, QDir::Time)) {
            LocalAnnotationDraft draft;
            if (info.absoluteFilePath() != m_path && readClosed(info.absoluteFilePath(), draft)
                && (entryId.isEmpty() || draft.note.entryId == entryId)) {
                drafts.append(std::move(draft));
            }
        }
        return drafts;
    }

    bool readClosed(const QString& path, LocalAnnotationDraft& draft) const
    {
        if (!safePath(path)) {
            return false;
        }
        QLockFile owner(path + QStringLiteral(".owner.lock"));
        if (!owner.tryLock(0)) {
            return false;
        }
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly) || file.size() > 128000) {
            return false;
        }
        QJsonParseError parseError;
        const auto doc = QJsonDocument::fromJson(file.readAll(), &parseError);
        if (file.error() != QFileDevice::NoError || parseError.error != QJsonParseError::NoError || !doc.isObject()) {
            return false;
        }
        const auto object = doc.object();
        const auto integer = [&object](const QString& field, int maximum) {
            const auto value = object.value(field);
            return value.isDouble() && value.toDouble() >= 0 && value.toDouble() <= maximum
                   && value.toDouble() == value.toInt(-1);
        };
        const auto schema = object.value(QStringLiteral("schema_version"));
        const bool legacy = schema.isDouble() && schema.toDouble() == 1.0;
        const bool current = schema.isDouble() && schema.toDouble() == 2.0;
        if ((!legacy && !current) || object.size() != (legacy ? 7 : 9)
            || (current && (!object.value(QStringLiteral("entry_title")).isString()
                            || !object.value(QStringLiteral("score_path")).isString()
                            || object.value(QStringLiteral("entry_title")).toString().size() > 512
                            || object.value(QStringLiteral("score_path")).toString().size() > 4096))
            || !object.value(QStringLiteral("entry_id")).isString() || !object.value(QStringLiteral("id")).isString()
            || !object.value(QStringLiteral("text")).isString() || !integer(QStringLiteral("revision"), 2147483647)
            || !integer(QStringLiteral("measure"), 999999) || !integer(QStringLiteral("page"), 999999)) {
            return false;
        }
        LocalLibraryAnnotation note { object.value(QStringLiteral("id")).toString(),
                                      object.value(QStringLiteral("entry_id")).toString(),
                                      object.value(QStringLiteral("text")).toString(),
                                      object.value(QStringLiteral("measure")).toInt(),
                                      object.value(QStringLiteral("page")).toInt(),
                                      object.value(QStringLiteral("revision")).toInt() };
        if (QUuid(note.entryId).isNull() || (!note.id.isEmpty() && QUuid(note.id).isNull()) || note.text.size() > 8000) {
            return false;
        }
        draft = { std::move(note), path, object.value(QStringLiteral("entry_title")).toString(),
                  object.value(QStringLiteral("score_path")).toString() };
        return true;
    }

    bool discardClosed(const QString& path, QString& error) const
    {
        if (path.isEmpty()) {
            return true;
        }
        if (!safePath(path)) {
            error = QStringLiteral("Cannot remove an unrecognized private-note recovery draft.");
            return false;
        }
        QLockFile owner(path + QStringLiteral(".owner.lock"));
        if (!owner.tryLock(0) || (QFileInfo::exists(path) && !QFile::remove(path))) {
            error = QStringLiteral("Cannot remove the private-note recovery draft.");
            return false;
        }
        return true;
    }

    // Explicit text copy, deliberately dropping source identity/revision and
    // manual references. A reused file path never causes an automatic match.
    static LocalLibraryAnnotation textCopyForEntry(const LocalAnnotationDraft& draft, const QString& entryId)
    {
        return { {}, entryId, draft.note.text, 0, 0, 0 };
    }

    QString filePath() const { return m_path; }

private:
    bool safePath(const QString& path) const
    {
        const QFileInfo info(path);
        return info.absolutePath() == QDir(m_folder).absolutePath() && info.suffix() == QStringLiteral("json")
               && !info.isSymLink() && !QUuid(info.completeBaseName()).isNull();
    }

    QString m_folder;
    QString m_path;
    std::unique_ptr<QLockFile> m_owner;
};
}
