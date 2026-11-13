// SPDX-License-Identifier: GPL-3.0-only
// QA prerequisite probe only; no application, registry or system trust changes.
#include <QCoreApplication>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSslSocket>
#include <QTemporaryDir>
#include <filesystem>
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv)
{
    QCoreApplication app(argc, argv);
    QJsonObject report{{"schema_version", 1}, {"qt_version", qVersion()},
                       {"supports_ssl", QSslSocket::supportsSsl()},
                       {"active_tls_backend", QSslSocket::activeBackend()},
                       {"available_tls_backends", QJsonArray::fromStringList(QSslSocket::availableBackends())},
                       {"physical_audio_or_gui_tested", false}, {"system_trust_changed", false}};
    bool links = false;
    QString error;
    {
        QTemporaryDir root;
        if (!root.isValid()) {
            error = QStringLiteral("Could not create prerequisite test directory");
        } else {
            try {
                const auto path = [&](const char* name) {
                    return std::filesystem::path(root.filePath(QString::fromLatin1(name)).toStdWString());
                };
                QFile target(root.filePath(QStringLiteral("target.wav")));
                if (!target.open(QIODevice::WriteOnly | QIODevice::NewOnly) || target.write("Q", 1) != 1) {
                    throw std::runtime_error("Could not create new prerequisite test file");
                }
                target.close();
                std::filesystem::create_symlink(path("target.wav"), path("file-link.wav"));
                std::filesystem::create_symlink(path("missing.wav"), path("dangling.wav"));
                std::filesystem::create_directory_symlink(path("."), path("directory-link"));
                links = std::filesystem::is_symlink(path("file-link.wav"))
                        && std::filesystem::is_symlink(path("dangling.wav"))
                        && std::filesystem::is_symlink(path("directory-link"));
            } catch (const std::exception& exception) {
                error = QString::fromUtf8(exception.what());
            }
        }
    }
    report.insert(QStringLiteral("ordinary_file_dangling_directory_symlinks_available"), links);
    report.insert(QStringLiteral("error"), error);
    const bool passed = report.value(QStringLiteral("supports_ssl")).toBool() && links;
    report.insert(QStringLiteral("passed"), passed);
    std::cout << QJsonDocument(report).toJson(QJsonDocument::Compact).constData() << '\n';
    return passed ? 0 : 1;
}
