// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
// Exercises the production installer with the exact two real CC0 banks.
// No download, user profile, audio device or application GUI is involved.
#include "freecollectioninstaller.h"

#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <iostream>
#include <stdexcept>

using namespace mu::musesounds;
namespace {
void check(bool condition, const char* message)
{
    if (!condition) { throw std::runtime_error(message); }
}
QByteArray read(const QString& path)
{
    QFile file(path);
    check(file.open(QIODevice::ReadOnly), "Cannot open fixture or installed file");
    return file.readAll();
}
QByteArray hash(const QString& path)
{
    QFile file(path);
    QCryptographicHash digest(QCryptographicHash::Sha256);
    check(file.open(QIODevice::ReadOnly) && digest.addData(&file) && file.error() == QFileDevice::NoError,
          "Cannot hash real fixture or installed file");
    return digest.result().toHex();
}
void write(const QString& path, const QByteArray& data)
{
    QFile file(path);
    check(file.open(QIODevice::WriteOnly | QIODevice::NewOnly) && file.write(data) == data.size() && file.flush(),
          "Cannot create owned test file");
}
bool import(FreeCollectionInstaller& installer, const FreeCollectionSpec& spec, const QString& source)
{
    QEventLoop loop;
    QTimer deadline;
    deadline.setSingleShot(true);
    bool done = false;
    bool ok = false;
    QObject::connect(&deadline, &QTimer::timeout, &loop, [&] { installer.cancel(); loop.quit(); });
    QObject::connect(&installer, &FreeCollectionInstaller::finished, &loop,
                     [&](bool result, const QString&) { done = true; ok = result; loop.quit(); });
    deadline.start(20000);
    installer.importFile(spec, source);
    if (!done) { loop.exec(); }
    return done && ok;
}
}
int main(int argc, char** argv)
{
    QCoreApplication application(argc, argv);
    if (argc != 3) {
        std::cerr << "Usage: local_only_collection_tests free-sound-collections.json exact-bank-directory\n";
        return 2;
    }
    int passed = 0;
    const auto run = [&](const char* name, auto operation) {
        operation(); ++passed; std::cout << "PASS: " << name << '\n';
    };
    try {
        const QString catalogue = QString::fromLocal8Bit(argv[1]);
        const QDir banks(QString::fromLocal8Bit(argv[2]));
        const QJsonObject document = QJsonDocument::fromJson(read(catalogue)).object();
        check(document.value("schema_version").toInt() == 1, "Unsupported catalogue fixture");
        const QByteArray license = read(QFileInfo(catalogue).dir().filePath("VSCO-CC0-LICENSE.txt"));
        check(QCryptographicHash::hash(license, QCryptographicHash::Sha256).toHex()
              == "36ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673", "CC0 text differs from verified source");
        QList<FreeCollectionSpec> specs;
        const QList<QString> names { "Cadence-VSCO-Flute.sf2", "Cadence-VSCO-Violin.sf2" };
        const QList<qint64> sizes { 16778410, 74366558 };
        const QList<QByteArray> hashes {
            "2bc48929d1996687b99e27b532043c4cb34b89480471faaea446ffc021ab3768",
            "801896ef3be53c4b60d9dc87078787add7fdc44b1a3bfe9fff30fcc519d93e0d"
        };
        const QList<QString> ids { "cadence-vsco-flute-1", "cadence-vsco-violin-1" };
        for (int index = 0; index < ids.size(); ++index) {
            QJsonObject record;
            for (const QJsonValue& value : document.value("collections").toArray()) {
                if (value.toObject().value("id").toString() == ids.at(index)) {
                    check(record.isEmpty(), "Duplicate new collection ID");
                    record = value.toObject();
                }
            }
            check(!record.isEmpty() && !record.value("builtin").toBool() && !record.contains("url"),
                  "Local-only collection is absent, built-in or advertises a URL");
            check(record.value("fileName").toString() == names.at(index)
                  && record.value("bytes").toDouble() == double(sizes.at(index))
                  && record.value("sha256").toString().toLatin1() == hashes.at(index),
                  "Catalogue identity differs from qualified real bank");
            const QJsonArray presets = record.value("instruments").toArray();
            const int program = index == 0 ? 73 : 40;
            check(presets.size() == 1 && presets.first().toObject().value("bank").toInt(-1) == 0
                  && presets.first().toObject().value("program").toInt(-1) == program
                  && record.value("resourceId").toString()
                     == QFileInfo(names.at(index)).completeBaseName() + QStringLiteral("\\0\\") + QString::number(program),
                  "Catalogue preset/resource differs from actual native Windows selection");
            check(record.value("licenseName").toString() == "CC0-1.0"
                  && record.value("sourceCommit").toString() == "28092772094b2d9f1148d84cea97f4545b8c687d",
                  "Unpinned source or incorrect licence");
            FreeCollectionSpec spec { ids.at(index), record.value("installationVersion").toString(),
                names.at(index), sizes.at(index), hashes.at(index), license, QUrl() };
            check(QFileInfo(banks.filePath(spec.fileName)).size() == spec.bytes
                  && hash(banks.filePath(spec.fileName)) == spec.sha256, "This test requires both exact real banks");
            specs.append(spec);
        }
        run("both local-only catalogue entries pin CC0, actual bytes and native presets", [] {});
        run("download without a public URL fails once before any folder or progress", [&] {
            for (const auto& spec : specs) {
                QTemporaryDir temporary;
                check(temporary.isValid(), "No owned test directory");
                const QString root = temporary.path() + "/absent";
                FreeCollectionInstaller installer(root);
                int finished = 0;
                int progress = 0;
                bool result = true;
                QString error;
                QObject::connect(&installer, &FreeCollectionInstaller::finished, &installer,
                                 [&](bool ok, const QString& message) { ++finished; result = ok; error = message; });
                QObject::connect(&installer, &FreeCollectionInstaller::progress, &installer,
                                 [&](qint64, qint64) { ++progress; });
                installer.download(spec);
                QCoreApplication::processEvents();
                check(finished == 1 && !result && error.contains(QString::fromUtf8("Téléchargement indisponible"))
                      && progress == 0 && !installer.busy() && !QFileInfo::exists(root), "Unavailable download mutated state");
            }
        });
        run("both exact real banks import, persist with CC0 and coexist; owned removal preserves siblings", [&] {
            QTemporaryDir temporary;
            check(temporary.isValid(), "No owned test directory");
            const QString root = temporary.path() + "/collections";
            check(QDir().mkpath(root + "/third-party"), "Cannot create sentinel directory");
            write(root + "/third-party/keep.sf2", "third-party unchanged");
            write(root + "/MS Basic.sf3", "base unchanged");
            FreeCollectionInstaller installer(root);
            for (const auto& spec : specs) {
                check(!installer.folder(spec).isEmpty(), "No-URL spec cannot resolve an owned folder");
                check(import(installer, spec, banks.filePath(spec.fileName)) && installer.installed(spec)
                      && FreeCollectionInstaller(root).installed(spec), "Real no-URL import or reopen failed");
                check(hash(installer.folder(spec) + "/" + spec.fileName) == spec.sha256
                      && read(installer.folder(spec) + "/LICENSE.txt") == license, "Installed bank or CC0 altered");
                const QJsonObject receipt = QJsonDocument::fromJson(read(installer.folder(spec) + "/receipt.json")).object();
                check(receipt.value("source").toString().isEmpty()
                      && receipt.value("sha256").toString().toLatin1() == spec.sha256, "Receipt invents a download source or loses identity");
            }
            QString error;
            check(installer.remove(specs.first(), &error) && !installer.installed(specs.first())
                  && installer.installed(specs.last()), "Removal affected the other bank");
            check(read(root + "/MS Basic.sf3") == "base unchanged"
                  && read(root + "/third-party/keep.sf2") == "third-party unchanged", "Other banks changed");
            check(installer.remove(specs.last(), &error), "Second owned removal failed");
        });
        run("wrong bank and same-size altered copy never become installed", [&] {
            QTemporaryDir temporary;
            check(temporary.isValid(), "No owned test directory");
            FreeCollectionInstaller installer(temporary.path() + "/collections");
            check(!import(installer, specs.first(), banks.filePath(specs.last().fileName))
                  && !QFileInfo::exists(installer.folder(specs.first())), "Wrong-sized bank accepted");
            const QString wrong = temporary.path() + "/wrong.sf2";
            check(QFile::copy(banks.filePath(specs.first().fileName), wrong), "Cannot copy owned wrong-hash fixture");
            QFile file(wrong);
            check(file.open(QIODevice::ReadWrite) && file.seek(file.size() - 1), "Cannot change owned fixture");
            char value = 0;
            check(file.getChar(&value) && file.seek(file.size() - 1) && file.putChar(char(value ^ 1)), "Cannot change final fixture byte");
            file.close();
            check(!import(installer, specs.first(), wrong) && !QFileInfo::exists(installer.folder(specs.first())),
                  "Same-size corrupt bank accepted");
        });
        run("existing local-only target and unknown content remain untouched", [&] {
            QTemporaryDir temporary;
            check(temporary.isValid(), "No owned test directory");
            FreeCollectionInstaller installer(temporary.path() + "/collections");
            check(QDir().mkpath(installer.folder(specs.first())), "Cannot create existing target");
            write(installer.folder(specs.first()) + "/personal.txt", "preserve");
            check(!import(installer, specs.first(), banks.filePath(specs.first().fileName))
                  && read(installer.folder(specs.first()) + "/personal.txt") == "preserve", "Existing target replaced");
            check(import(installer, specs.last(), banks.filePath(specs.last().fileName)), "Second import failed");
            write(installer.folder(specs.last()) + "/personal.txt", "preserve");
            QString error;
            check(!installer.remove(specs.last(), &error) && !error.isEmpty()
                  && hash(installer.folder(specs.last()) + "/" + specs.last().fileName) == specs.last().sha256,
                  "Unknown content or bank removed");
        });
        run("live lock blocks local-only import and permits retry after release", [&] {
            QTemporaryDir temporary;
            check(temporary.isValid(), "No owned test directory");
            const QString root = temporary.path() + "/collections";
            check(QDir().mkpath(root), "Cannot create lock fixture");
            QLockFile lock(root + "/" + specs.first().id + ".lock");
            check(lock.tryLock(0), "Cannot acquire test lock");
            FreeCollectionInstaller installer(root);
            check(!import(installer, specs.first(), banks.filePath(specs.first().fileName)), "Concurrent locked import accepted");
            lock.unlock();
            check(import(installer, specs.first(), banks.filePath(specs.first().fileName)), "Retry after release failed");
        });
        run("unavailable download requested during a real import leaves it running", [&] {
            QTemporaryDir temporary;
            check(temporary.isValid(), "No owned test directory");
            FreeCollectionInstaller installer(temporary.path() + "/collections");
            int finished = 0;
            bool attempted = false;
            QObject::connect(&installer, &FreeCollectionInstaller::finished, &installer,
                             [&](bool, const QString&) { ++finished; });
            QObject::connect(&installer, &FreeCollectionInstaller::progress, &installer, [&](qint64 current, qint64) {
                if (current > 0 && !attempted) { attempted = true; installer.download(specs.first()); }
            });
            check(import(installer, specs.last(), banks.filePath(specs.last().fileName))
                  && attempted && finished == 1 && installer.installed(specs.last()), "Unavailable request interrupted active import");
        });
        run("URL policy still rejects unsafe nonempty sources and accepts pinned HTTPS", [&] {
            QTemporaryDir temporary;
            check(temporary.isValid(), "No owned test directory");
            const QString root = temporary.path() + "/absent";
            FreeCollectionInstaller installer(root);
            auto spec = specs.first();
            for (const QString& url : QStringList { "http://raw.githubusercontent.com/x", "https://example.test/x",
                    "https://user@raw.githubusercontent.com/x", "https://raw.githubusercontent.com:443/x",
                    "https://raw.githubusercontent.com/x?q=1", "https://raw.githubusercontent.com/x#fragment" }) {
                spec.downloadUrl = QUrl(url);
                check(installer.folder(spec).isEmpty() && !import(installer, spec, banks.filePath(spec.fileName))
                      && !QFileInfo::exists(root), "Unsafe nonempty URL became valid");
            }
            spec.downloadUrl = QUrl("https://raw.githubusercontent.com/pinned/repo/commit/file.sf2");
            check(!installer.folder(spec).isEmpty(), "Existing allowed download source policy regressed");
        });
        for (const auto& spec : specs) {
            check(hash(banks.filePath(spec.fileName)) == spec.sha256, "Original qualified bank was altered");
        }
        std::cout << passed << "/8 local-only production installer scenarios passed (Qt " << qVersion() << ").\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n'; return 1;
    }
}
