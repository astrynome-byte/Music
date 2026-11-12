// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <QCryptographicHash>
#include <QFile>
#include <QLockFile>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QObject>
#include <QTemporaryDir>
#include <QTimer>
#include <QUrl>
#include <memory>

namespace mu::musesounds {
struct FreeCollectionSpec {
    QString id;
    QString version;
    QString fileName;
    qint64 bytes = 0;
    QByteArray sha256;
    QByteArray license;
    QUrl downloadUrl;
};

// Installs only a single pinned SF2/SF3 and its notices in an owned directory.
// It neither edits score files nor replaces the application's built-in bank.
class FreeCollectionInstaller : public QObject
{
    Q_OBJECT
public:
    explicit FreeCollectionInstaller(QString root, QObject* parent = nullptr);
    ~FreeCollectionInstaller() override;
    bool busy() const { return m_busy; }
    QString folder(const FreeCollectionSpec& spec) const;
    bool installed(const FreeCollectionSpec& spec, QString* error = nullptr) const;
    bool remove(const FreeCollectionSpec& spec, QString* error);
    void download(const FreeCollectionSpec& spec);
    void importFile(const FreeCollectionSpec& spec, const QString& source);
    void cancel();

signals:
    void progress(qint64 received, qint64 total);
    void finished(bool ok, const QString& error);

private:
    bool begin(const FreeCollectionSpec& spec);
    bool consume(const QByteArray& bytes);
    void copyNext();
    void complete();
    void finish(bool ok, const QString& error);
    bool safeRoot(QString* error, bool create) const;
    bool validSpec(const FreeCollectionSpec& spec) const;
    QString m_root;
    FreeCollectionSpec m_spec;
    std::unique_ptr<QTemporaryDir> m_temporary;
    std::unique_ptr<QLockFile> m_lock;
    QFile m_output;
    QFile m_source;
    QNetworkAccessManager m_network;
    QNetworkReply* m_reply = nullptr;
    QTimer m_copyTimer;
    QTimer m_deadline;
    QCryptographicHash m_hash { QCryptographicHash::Sha256 };
    qint64 m_received = 0;
    bool m_busy = false;
    quint64 m_generation = 0;
};
}
