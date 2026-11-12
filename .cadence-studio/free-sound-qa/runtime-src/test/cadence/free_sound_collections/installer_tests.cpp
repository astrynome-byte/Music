// SPDX-License-Identifier: GPL-3.0-only
#include "freecollectioninstaller.h"
#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPointer>
#include <QTemporaryDir>
#include <QTimer>
#include <functional>
#include <iostream>
#include <stdexcept>
using namespace mu::musesounds;
namespace {
void check(bool value, const char* error) { if (!value) { throw std::runtime_error(error); } }
QByteArray hash(const QString& path) { QFile f(path); QCryptographicHash h(QCryptographicHash::Sha256); check(f.open(QIODevice::ReadOnly) && h.addData(&f), "Cannot hash fixture"); return h.result().toHex(); }
void write(const QString& path, const QByteArray& bytes) { QFile f(path); check(f.open(QIODevice::WriteOnly) && f.write(bytes) == bytes.size(), "Cannot write temporary fixture"); }
bool import(FreeCollectionInstaller& installer, const FreeCollectionSpec& spec, const QString& source, bool cancel = false)
{
    QEventLoop loop;
    bool result = false;
    bool done = false;
    const auto connection = QObject::connect(&installer, &FreeCollectionInstaller::finished, &loop, [&](bool ok, const QString&) { result = ok; done = true; loop.quit(); });
    QTimer deadline; deadline.setSingleShot(true);
    QObject::connect(&deadline, &QTimer::timeout, &loop, [&] { installer.cancel(); loop.quit(); });
    deadline.start(10000);
    installer.importFile(spec, source);
    if (cancel) { installer.cancel(); }
    if (!done) { loop.exec(); }
    QObject::disconnect(connection);
    check(done, "Installer did not complete within its test deadline");
    check(!installer.busy(), "Installer stayed busy after completion");
    return result;
}
}
int main(int argc, char** argv)
{
    QCoreApplication application(argc, argv);
    if (argc != 3 && argc != 4) { std::cerr << "Usage: installer_tests fixture.sf2 license.txt [--download-real]\n"; return 2; }
    const bool downloadReal = argc == 4 && QByteArray(argv[3]) == QByteArrayLiteral("--download-real");
    if (argc == 4 && !downloadReal) { return 2; }
    const QString source = QString::fromLocal8Bit(argv[1]);
    QFile license(QString::fromLocal8Bit(argv[2]));
    check(license.open(QIODevice::ReadOnly), "Cannot read exact upstream licence");
    const auto originalHash = hash(source);
    const FreeCollectionSpec spec { QStringLiteral("generaluser-gs-2-0-3"), QStringLiteral("2.0.3"), QStringLiteral("Cadence-GeneralUser-GS-2.0.3.sf2"),
        32319396, QByteArrayLiteral("9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe"), license.readAll(),
        QUrl(QStringLiteral("https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/684543d5e5efaef08d02be50dcda8d552478fa60/GeneralUser-GS.sf2")) };
    check(originalHash == spec.sha256, "This test requires the exact real optional bank");
    int passed = 0;
    auto run = [&](const char* name, const std::function<void()>& test) { test(); ++passed; std::cout << "PASS: " << name << '\n'; };
    try {
        run("real bank imported in chunks, source preserved, notices and receipt, reopen and owned uninstall", [&] {
            QTemporaryDir temporary; check(temporary.isValid(), "No temporary directory");
            const QString root = temporary.path() + QString::fromUtf8("/Profil été/Collections");
            FreeCollectionInstaller installer(root);
            check(import(installer, spec, source), "Real bank import failed");
            check(installer.installed(spec), "Committed bank did not pass exact receipt/hash verification");
            check(FreeCollectionInstaller(root).installed(spec), "A new installer did not recognize persisted bank");
            check(hash(source) == originalHash, "Original source bank changed");
            check(hash(installer.folder(spec) + "/LICENSE.txt") == QCryptographicHash::hash(spec.license, QCryptographicHash::Sha256).toHex(), "Licence altered");
            write(root + "/user-kept.txt", "keep"); QString error;
            check(installer.remove(spec, &error), "Owned uninstall failed");
            check(!installer.installed(spec) && QFile::exists(root + "/user-kept.txt"), "Uninstall touched unrelated content or left bank installed");
        });
        run("hash mismatch refuses all final installation and preserves source", [&] {
            QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
            auto wrong = spec; wrong.sha256 = QByteArray(64, '0');
            check(!import(installer, wrong, source), "Wrong SHA was accepted");
            check(!QFile::exists(installer.folder(wrong)) && hash(source) == originalHash, "Failed SHA damaged source or committed bank");
        });
        run("cancellation before first copy event creates no installed bank", [&] {
            QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
            check(!import(installer, spec, source, true) && !QFile::exists(installer.folder(spec)), "Cancellation committed a bank");
        });
        run("existing collection directory is never replaced", [&] {
            QTemporaryDir temporary; const QString root = temporary.path() + "/collections";
            FreeCollectionInstaller installer(root); QDir().mkpath(installer.folder(spec));
            write(installer.folder(spec) + "/personal.txt", "keep");
            check(!import(installer, spec, source), "Existing directory replaced");
            check(QFile::exists(installer.folder(spec) + "/personal.txt"), "Existing user file removed");
        });
        run("unknown added file blocks uninstall without deleting the real bank", [&] {
            QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
            check(import(installer, spec, source), "Initial import failed");
            write(installer.folder(spec) + "/private.txt", "preserve"); QString error;
            check(!installer.remove(spec, &error) && !error.isEmpty(), "Unknown content was not refused");
            check(hash(installer.folder(spec) + "/" + spec.fileName) == originalHash, "Bank changed on refused uninstall");
        });
        run("modified bank blocks uninstall and leaves its bytes intact", [&] {
            QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
            check(import(installer, spec, source), "Initial import failed");
            const QString file = installer.folder(spec) + "/" + spec.fileName;
            QFile changed(file); check(changed.open(QIODevice::ReadWrite), "Cannot modify test copy"); check(changed.seek(100), "Cannot seek"); check(changed.write("changed", 7) == 7, "Cannot alter test copy"); changed.close();
            const auto modified = hash(file); QString error;
            check(modified != originalHash && !installer.remove(spec, &error) && hash(file) == modified, "Modified bank was removed");
        });
        run("real lock prevents concurrent installation", [&] {
            QTemporaryDir temporary; const QString root = temporary.path() + "/collections"; QDir().mkpath(root);
            QLockFile lock(root + "/" + spec.id + ".lock"); check(lock.tryLock(0), "Cannot hold test lock");
            FreeCollectionInstaller installer(root); check(!import(installer, spec, source), "Concurrent locked import accepted");
            lock.unlock(); check(import(installer, spec, source), "Lock was not released for later import");
        });
        run("invalid ID refuses traversal before any root directory is created", [&] {
            QTemporaryDir temporary; const QString root = temporary.path() + "/new-root"; FreeCollectionInstaller installer(root);
            auto invalid = spec; invalid.id = QStringLiteral("../escape");
            check(!import(installer, invalid, source) && !QFile::exists(root), "Invalid ID caused filesystem changes");
        });
        run("non-directory parent fails without replacing that file", [&] {
            QTemporaryDir temporary; const QString parent = temporary.path() + "/file"; write(parent, "preserve");
            FreeCollectionInstaller installer(parent + "/collections");
            check(!import(installer, spec, source) && QFileInfo(parent).isFile(), "Parent file was replaced");
        });
        run("synchronous cancellation at initial progress starts no copy and finishes once", [&] {
            QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
            int finishedCount = 0; int progressCount = 0;
            QObject::connect(&installer, &FreeCollectionInstaller::finished, &application, [&](bool, const QString&) { ++finishedCount; });
            QObject::connect(&installer, &FreeCollectionInstaller::progress, &application, [&](qint64, qint64) { ++progressCount; installer.cancel(); });
            check(!import(installer, spec, source), "Synchronous zero-progress cancellation ignored");
            QCoreApplication::processEvents();
            check(finishedCount == 1 && progressCount == 1 && !QFile::exists(installer.folder(spec)), "Cancelled import continued or finished twice");
        });
        run("synchronous cancellation after a real data chunk finishes once", [&] {
            QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
            int finishedCount = 0; bool sawChunk = false;
            QObject::connect(&installer, &FreeCollectionInstaller::finished, &application, [&](bool, const QString&) { ++finishedCount; });
            QObject::connect(&installer, &FreeCollectionInstaller::progress, &application, [&](qint64 bytes, qint64) { if (bytes > 0) { sawChunk = true; installer.cancel(); } });
            check(!import(installer, spec, source), "Chunk cancellation ignored");
            QCoreApplication::processEvents();
            check(sawChunk && finishedCount == 1 && !QFile::exists(installer.folder(spec)), "Chunk cancellation continued or finished twice");
        });
        run("destruction from initial progress does not access the deleted installer", [&] {
            QTemporaryDir temporary;
            auto* installer = new FreeCollectionInstaller(temporary.path() + "/collections");
            QPointer<FreeCollectionInstaller> pointer(installer);
            QObject::connect(installer, &FreeCollectionInstaller::progress, &application, [installer](qint64, qint64) { delete installer; });
            installer->importFile(spec, source);
            check(pointer.isNull(), "Progress did not destroy the owned test installer");
            check(!QFile::exists(temporary.path() + "/collections/" + spec.id), "Destroyed import committed a bank");
        });
        run("a new import started during cancellation is not resumed as the old operation", [&] {
            QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
            bool cancelledFirst = false; bool secondSucceeded = false; int finishedCount = 0;
            QEventLoop loop; QTimer deadline; deadline.setSingleShot(true);
            QObject::connect(&deadline, &QTimer::timeout, &loop, &QEventLoop::quit);
            QObject::connect(&installer, &FreeCollectionInstaller::progress, &application, [&](qint64, qint64) { if (!cancelledFirst) { cancelledFirst = true; installer.cancel(); } });
            QObject::connect(&installer, &FreeCollectionInstaller::finished, &loop, [&](bool ok, const QString&) {
                ++finishedCount;
                if (finishedCount == 1) { installer.importFile(spec, source); }
                else { secondSucceeded = ok; loop.quit(); }
            });
            installer.importFile(spec, source); deadline.start(10000); loop.exec();
            check(secondSucceeded && finishedCount == 2 && installer.installed(spec), "Reentrant replacement operation failed");
        });
        if (downloadReal) {
            run("explicit real HTTPS download by the production Qt Network installer", [&] {
                QTemporaryDir temporary; FreeCollectionInstaller installer(temporary.path() + "/collections");
                QEventLoop loop; QTimer deadline; deadline.setSingleShot(true);
                bool done = false; bool ok = false;
                QObject::connect(&deadline, &QTimer::timeout, &loop, [&] { installer.cancel(); loop.quit(); });
                QObject::connect(&installer, &FreeCollectionInstaller::finished, &loop, [&](bool result, const QString& error) { done = true; ok = result; if (!result) { std::cerr << error.toStdString() << '\n'; } loop.quit(); });
                deadline.start(190000); installer.download(spec); if (!done) { loop.exec(); }
                check(done && ok && installer.installed(spec), "Production HTTPS download was not verified and committed");
            });
        }
        check(hash(source) == originalHash, "Original real SoundFont changed after all scenarios");
        std::cout << passed << "/" << (downloadReal ? 14 : 13) << " real installer scenarios passed (Qt " << qVersion() << ").\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << "FAIL: " << error.what() << '\n'; return 1; }
}
