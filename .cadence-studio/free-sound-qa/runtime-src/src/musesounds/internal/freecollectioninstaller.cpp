// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#include "freecollectioninstaller.h"

#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkRequest>
#include <QPointer>
#include <QRegularExpression>
#include <QStorageInfo>

using namespace mu::musesounds;
namespace {
QString text(const char* source) { return QString::fromUtf8(source); }
bool plainAncestors(QString path)
{
    while (!path.isEmpty()) {
        const QFileInfo info(path);
        if (info.isSymLink()
#ifdef Q_OS_WIN
            || info.isJunction()
#endif
            ) { return false; }
        const QString parent = info.absolutePath();
        if (parent == path) { break; }
        path = parent;
    }
    return true;
}
QByteArray hashFile(const QString& path)
{
    QFile file(path);
    QCryptographicHash hash(QCryptographicHash::Sha256);
    return file.open(QIODevice::ReadOnly) && hash.addData(&file) && file.error() == QFileDevice::NoError
           ? hash.result().toHex() : QByteArray();
}
bool writeNew(const QString& path, const QByteArray& bytes)
{
    QFile file(path);
    return file.open(QIODevice::WriteOnly | QIODevice::NewOnly) && file.write(bytes) == bytes.size() && file.flush();
}
}

FreeCollectionInstaller::FreeCollectionInstaller(QString root, QObject* parent)
    : QObject(parent), m_root(QDir::cleanPath(root))
{
    m_copyTimer.setInterval(0);
    connect(&m_copyTimer, &QTimer::timeout, this, &FreeCollectionInstaller::copyNext);
    m_deadline.setSingleShot(true);
    connect(&m_deadline, &QTimer::timeout, this, [this] {
        finish(false, text("Le téléchargement a dépassé son délai. Réessayez ou importez le fichier hors ligne."));
    });
}
FreeCollectionInstaller::~FreeCollectionInstaller()
{
    if (m_reply) { m_reply->disconnect(this); m_reply->abort(); }
}

bool FreeCollectionInstaller::validSpec(const FreeCollectionSpec& spec) const
{
    static const QRegularExpression id(QStringLiteral("^[a-z0-9][a-z0-9-]{0,63}$"));
    static const QRegularExpression name(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9 ._-]{0,95}\\.(sf2|sf3)$"));
    static const QRegularExpression sha(QStringLiteral("^[a-f0-9]{64}$"));
    return id.match(spec.id).hasMatch() && name.match(spec.fileName).hasMatch()
           && sha.match(QString::fromLatin1(spec.sha256)).hasMatch()
           && spec.bytes >= 1024 && spec.bytes <= 268435456 && !spec.version.isEmpty()
           && !spec.license.isEmpty() && spec.license.size() <= 65536
           && spec.downloadUrl.scheme() == QStringLiteral("https")
           && spec.downloadUrl.host() == QStringLiteral("raw.githubusercontent.com")
           && spec.downloadUrl.userInfo().isEmpty() && spec.downloadUrl.port(-1) == -1
           && !spec.downloadUrl.hasQuery() && !spec.downloadUrl.hasFragment();
}
bool FreeCollectionInstaller::safeRoot(QString* error, bool create) const
{
    if (!QFileInfo(m_root).isAbsolute() || !plainAncestors(m_root)) {
        *error = text("Le dossier des collections doit être un dossier local sans lien symbolique."); return false;
    }
    if (QFileInfo::exists(m_root) && !QFileInfo(m_root).isDir()) {
        *error = text("Un fichier occupe le dossier des collections."); return false;
    }
    if (create && !QDir().mkpath(m_root)) {
        *error = text("Impossible de créer le dossier des collections. Vérifiez ses droits d'accès."); return false;
    }
    return true;
}
QString FreeCollectionInstaller::folder(const FreeCollectionSpec& spec) const
{
    return validSpec(spec) ? QDir(m_root).filePath(spec.id) : QString();
}
bool FreeCollectionInstaller::installed(const FreeCollectionSpec& spec, QString* error) const
{
    QString localError;
    if (!error) { error = &localError; }
    error->clear();
    if (!validSpec(spec) || !safeRoot(error, false)) { return false; }
    const QString directory = folder(spec);
    if (!QFileInfo::exists(directory)) { return false; }
    if (!QFileInfo(directory).isDir() || !plainAncestors(directory)) {
        *error = text("Le dossier de cette collection est invalide. Aucun fichier n'a été modifié."); return false;
    }
    const QDir dir(directory);
    QStringList expected { spec.fileName, QStringLiteral("LICENSE.txt"), QStringLiteral("receipt.json") };
    expected.sort();
    QStringList actual = dir.entryList(QDir::AllEntries | QDir::Hidden | QDir::System | QDir::NoDotAndDotDot, QDir::Name);
    actual.sort();
    if (actual != expected) {
        *error = text("Des fichiers inattendus sont présents dans la collection. Ils sont conservés."); return false;
    }
    for (const QString& name : expected) {
        const QFileInfo info(dir.filePath(name));
        if (!info.isFile() || info.isSymLink() || !plainAncestors(info.absoluteFilePath())) {
            *error = text("Le contenu de cette collection ne correspond plus à son installation."); return false;
        }
    }
    QFile receipt(dir.filePath(QStringLiteral("receipt.json")));
    if (receipt.size() > 16384 || !receipt.open(QIODevice::ReadOnly)) {
        *error = text("Le reçu d'installation est illisible."); return false;
    }
    const QJsonObject record = QJsonDocument::fromJson(receipt.readAll()).object();
    if (record.value(QStringLiteral("schema_version")).toInt() != 1
        || record.value(QStringLiteral("id")).toString() != spec.id
        || record.value(QStringLiteral("sha256")).toString().toLatin1() != spec.sha256
        || record.value(QStringLiteral("version")).toString() != spec.version
        || record.value(QStringLiteral("file")).toString() != spec.fileName
        || record.value(QStringLiteral("bytes")).toDouble() != double(spec.bytes)
        || QFileInfo(dir.filePath(spec.fileName)).size() != spec.bytes
        || hashFile(dir.filePath(spec.fileName)) != spec.sha256
        || hashFile(dir.filePath(QStringLiteral("LICENSE.txt"))) != QCryptographicHash::hash(spec.license, QCryptographicHash::Sha256).toHex()) {
        *error = text("La collection ou son reçu a été modifié. Aucun remplacement ni retrait automatique."); return false;
    }
    return true;
}

bool FreeCollectionInstaller::begin(const FreeCollectionSpec& spec)
{
    if (m_busy) { return false; }
    QString error;
    if (!validSpec(spec) || !safeRoot(&error, true)) {
        emit finished(false, error.isEmpty() ? text("Le catalogue de cette collection est invalide.") : error); return false;
    }
    m_lock = std::make_unique<QLockFile>(QDir(m_root).filePath(spec.id + QStringLiteral(".lock")));
    if (!m_lock->tryLock(0)) {
        m_lock.reset(); emit finished(false, text("Une autre fenêtre installe ou retire cette collection.")); return false;
    }
    if (QFileInfo::exists(folder(spec))) {
        m_lock.reset(); emit finished(false, text("Ce dossier existe déjà. Aucun fichier existant n'est remplacé.")); return false;
    }
    const QStorageInfo storage(m_root);
    if (!storage.isValid() || !storage.isReady() || storage.bytesAvailable() < spec.bytes + 1048576) {
        m_lock.reset(); emit finished(false, text("L'espace libre est insuffisant pour installer cette collection.")); return false;
    }
    m_spec = spec;
    m_temporary = std::make_unique<QTemporaryDir>(QDir(m_root).filePath(QStringLiteral(".incoming-XXXXXX")));
    if (!m_temporary->isValid()) {
        m_temporary.reset(); m_lock.reset(); emit finished(false, text("Impossible de préparer le dossier temporaire.")); return false;
    }
    m_output.setFileName(QDir(m_temporary->path()).filePath(spec.fileName));
    if (!m_output.open(QIODevice::WriteOnly | QIODevice::NewOnly)) {
        m_temporary.reset(); m_lock.reset(); emit finished(false, text("Impossible d'écrire la collection.")); return false;
    }
    m_hash.reset(); m_received = 0; m_busy = true;
    const quint64 generation = ++m_generation;
    QPointer<FreeCollectionInstaller> guard(this);
    emit progress(0, spec.bytes);
    return guard && guard->m_busy && guard->m_generation == generation;
}
bool FreeCollectionInstaller::consume(const QByteArray& bytes)
{
    if (!m_busy) { return false; }
    if (bytes.size() > m_spec.bytes - m_received || m_output.write(bytes) != bytes.size()) {
        finish(false, text("La taille téléchargée est incorrecte ou l'écriture a échoué.")); return false;
    }
    m_hash.addData(bytes); m_received += bytes.size();
    const quint64 generation = m_generation;
    QPointer<FreeCollectionInstaller> guard(this);
    emit progress(m_received, m_spec.bytes);
    return guard && guard->m_busy && guard->m_generation == generation;
}
void FreeCollectionInstaller::download(const FreeCollectionSpec& spec)
{
    if (!begin(spec)) { return; }
    QNetworkRequest request(spec.downloadUrl);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setTransferTimeout(60000);
    const quint64 generation = m_generation;
    QNetworkReply* reply = m_network.get(request);
    m_reply = reply;
    reply->setReadBufferSize(1048576);
    connect(reply, &QIODevice::readyRead, this, [this, reply, generation] {
        if (m_reply != reply || !m_busy || m_generation != generation) { return; }
        while (reply->bytesAvailable() > 0) {
            if (!consume(reply->read(1048576))) { return; }
        }
    });
    connect(reply, &QNetworkReply::finished, this, [this, reply, generation] {
        if (m_reply != reply || !m_busy || m_generation != generation) { return; }
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if (reply->error() != QNetworkReply::NoError || status != 200 || reply->url() != m_spec.downloadUrl) {
            finish(false, text("Le téléchargement a échoué. Le fichier attendu n'a pas été installé.")); return;
        }
        const QByteArray tail = reply->readAll();
        if (!consume(tail)) { return; }
        complete();
    });
    m_deadline.start(180000);
}
void FreeCollectionInstaller::importFile(const FreeCollectionSpec& spec, const QString& source)
{
    if (!begin(spec)) { return; }
    m_source.setFileName(source);
    if (!m_source.open(QIODevice::ReadOnly) || m_source.size() != spec.bytes) {
        finish(false, text("Choisissez le fichier de la version annoncée, de taille et d'empreinte correspondantes.")); return;
    }
    m_copyTimer.start();
}
void FreeCollectionInstaller::copyNext()
{
    if (!m_busy) { return; }
    const QByteArray bytes = m_source.read(1048576);
    if (m_source.error() != QFileDevice::NoError) { finish(false, text("La lecture du fichier importé a échoué.")); return; }
    if (!consume(bytes)) { return; }
    if (m_source.atEnd()) { complete(); }
}
void FreeCollectionInstaller::complete()
{
    if (!m_busy || !m_temporary) { return; }
    if (m_received != m_spec.bytes || m_hash.result().toHex() != m_spec.sha256 || !m_output.flush()) {
        finish(false, text("L'empreinte ou la taille ne correspond pas au catalogue. Le fichier n'a pas été installé.")); return;
    }
    m_output.close(); m_source.close(); m_copyTimer.stop();
    QFile bank(m_output.fileName());
    if (!bank.open(QIODevice::ReadOnly) || bank.read(4) != QByteArrayLiteral("RIFF")
        || !bank.seek(8) || bank.read(4) != QByteArrayLiteral("sfbk")) {
        finish(false, text("Le fichier vérifié n'est pas une banque SoundFont valide.")); return;
    }
    bank.close();
    const QJsonObject record {
        { QStringLiteral("schema_version"), 1 }, { QStringLiteral("id"), m_spec.id },
        { QStringLiteral("version"), m_spec.version }, { QStringLiteral("file"), m_spec.fileName },
        { QStringLiteral("bytes"), double(m_spec.bytes) }, { QStringLiteral("sha256"), QString::fromLatin1(m_spec.sha256) },
        { QStringLiteral("source"), m_spec.downloadUrl.toString() }
    };
    const QDir temporary(m_temporary->path());
    if (!writeNew(temporary.filePath(QStringLiteral("LICENSE.txt")), m_spec.license)
        || !writeNew(temporary.filePath(QStringLiteral("receipt.json")), QJsonDocument(record).toJson())) {
        finish(false, text("Impossible d'enregistrer la licence et le reçu. Installation annulée.")); return;
    }
    const QString name = QFileInfo(m_temporary->path()).fileName();
    if (!plainAncestors(m_root) || QFileInfo::exists(folder(m_spec)) || !QDir(m_root).rename(name, m_spec.id)) {
        finish(false, text("Le dossier final n'est pas disponible. Aucun fichier existant n'a été remplacé.")); return;
    }
    m_temporary->setAutoRemove(false);
    finish(true, QString());
}
void FreeCollectionInstaller::finish(bool ok, const QString& error)
{
    m_copyTimer.stop(); m_deadline.stop();
    if (m_reply) {
        QNetworkReply* reply = m_reply; m_reply = nullptr;
        reply->disconnect(this); if (!reply->isFinished()) { reply->abort(); } reply->deleteLater();
    }
    m_output.close(); m_source.close(); m_temporary.reset(); m_lock.reset(); m_busy = false;
    ++m_generation;
    emit finished(ok, error);
}
void FreeCollectionInstaller::cancel()
{
    if (m_busy) { finish(false, text("Installation annulée. Les partitions et les sons de base sont inchangés.")); }
}
bool FreeCollectionInstaller::remove(const FreeCollectionSpec& spec, QString* error)
{
    QString localError;
    if (!error) { error = &localError; }
    error->clear();
    if (m_busy) { *error = text("Terminez l'installation en cours avant de retirer une collection."); return false; }
    if (!installed(spec, error)) { if (error->isEmpty()) { *error = text("Cette collection n'est pas installée."); } return false; }
    QLockFile lock(QDir(m_root).filePath(spec.id + QStringLiteral(".lock")));
    if (!lock.tryLock(0)) { *error = text("Une autre fenêtre utilise le gestionnaire de cette collection."); return false; }
    if (!installed(spec, error)) { return false; }
    const QDir directory(folder(spec));
    // Bank first: if Windows keeps it open, notices/receipt remain intact.
    if (!QFile::remove(directory.filePath(spec.fileName))) {
        *error = text("Cette banque est encore utilisée ou protégée. Fermez les autres fenêtres puis réessayez."); return false;
    }
    bool ok = QFile::remove(directory.filePath(QStringLiteral("LICENSE.txt")));
    ok = QFile::remove(directory.filePath(QStringLiteral("receipt.json"))) && ok;
    ok = QDir(m_root).rmdir(spec.id) && ok;
    if (!ok) { *error = text("La banque a été retirée ; son dossier contient encore des fichiers à conserver ou à retirer manuellement."); }
    return ok;
}
