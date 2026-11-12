// SPDX-License-Identifier: GPL-3.0-only
// Diagnostic experiment, not an application or an assertion that a GUI fix works.
#include "localscorelibrarystore.h"
#include "localcatalogwatch.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFile>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QStandardPaths>
#include <QStorageInfo>
#include <QTemporaryDir>
#include <QThread>
#include <QTimer>
#include <atomic>
#include <chrono>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <thread>

#ifdef Q_OS_WIN
#include <aclapi.h>
#include <sddl.h>
#endif

using namespace mu::project;
namespace {
void require(bool condition, const char* detail) { if (!condition) { throw std::runtime_error(detail); } }
QByteArray read(const QString& path)
{
    QFile file(path);
    require(file.open(QIODevice::ReadOnly), "Cannot read a controlled fixture after stopping its watcher");
    return file.readAll();
}
QByteArray hash(const QString& path) { return QCryptographicHash::hash(read(path), QCryptographicHash::Sha256).toHex(); }
void write(const QString& path, const QByteArray& bytes)
{
    QFile file(path);
    require(file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size(), "Cannot create controlled score fixture");
}
struct Phase {
    QJsonObject report;
    int failures = 0;
    bool preservation = false;
    int overlappedCallbacks = 0;
};
QJsonObject locationMetadata(const QString& path)
{
    // Capture directory metadata/rights before any watcher/writer starts.
    const QStorageInfo volume(path);
    const QFileInfo info(path);
    QJsonObject result { { "fixture_parent", path }, { "volume_root", volume.rootPath() },
                         { "volume_device", QString::fromLocal8Bit(volume.device()) },
                         { "filesystem_type", QString::fromLatin1(volume.fileSystemType()) },
                         { "volume_name", volume.name() }, { "volume_read_only", volume.isReadOnly() },
                         { "qt_directory_permissions", int(info.permissions()) } };
#ifdef Q_OS_WIN
    const auto native = QDir::toNativeSeparators(path);
    result["native_attributes"] = int(GetFileAttributesW(reinterpret_cast<LPCWSTR>(native.utf16())));
    result["ntfs_permission_checks_enabled"] = qAreNtfsPermissionChecksEnabled();
    PSECURITY_DESCRIPTOR descriptor = nullptr;
    const DWORD status = GetNamedSecurityInfoW(reinterpret_cast<LPWSTR>(const_cast<ushort*>(native.utf16())),
                                               SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                                               nullptr, nullptr, nullptr, nullptr, &descriptor);
    result["directory_security_query_status"] = int(status);
    if (status == ERROR_SUCCESS && descriptor) {
        LPWSTR text = nullptr;
        if (ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, SDDL_REVISION_1,
            OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION, &text, nullptr)) {
            const auto value = QString::fromWCharArray(text);
            result["directory_security_sddl"] = value.left(4096);
            result["directory_security_sddl_truncated"] = value.size() > 4096;
            LocalFree(text);
        } else { result["directory_security_format_error"] = int(GetLastError()); }
        LocalFree(descriptor);
    }
#endif
    return result;
}
Phase runPhase(const QString& location, const QString& baseRoot, const QString& mode, int round, int iterations, int budgetMs)
{
    QTemporaryDir temporary(QDir(baseRoot).filePath(QStringLiteral("cadence-watch-diagnostic-XXXXXX")));
    require(temporary.isValid(), "No temporary fixture directory");
    const auto locationInfo = locationMetadata(temporary.path());
    const QString scorePath = temporary.path() + QStringLiteral("/original.mscx");
    const QByteArray original("<museScore version=\"4.40\"><Score><metaTag name=\"workTitle\">Diagnostic original</metaTag></Score></museScore>\n");
    write(scorePath, original);
    const QByteArray originalHash = hash(scorePath);
    const QString catalogue = temporary.path() + QStringLiteral("/library.json");
    LocalScoreLibraryStore initial(catalogue);
    const auto created = initial.add({ { {}, scorePath, QStringLiteral("Diagnostic original"), QStringLiteral("Cadence QA"), false } });
    require(created.ok && created.entries.size() == 1, "Cannot prepare a schema1 catalogue before watching");
    const QString entryId = created.entries[0].id;

    std::atomic<bool> inMutation {false}, done {false};
    int fileEvents = 0, directoryEvents = 0, stampChanges = 0, callbacksDuringMutation = 0, rearms = 0;
    int attempts = 0, successes = 0, failures = 0, enableAttempts = 0, enableSuccesses = 0;
    bool expectedFavorite = false;
    int expectedSchema = 1;
    bool budgetReached = false;
    QJsonArray errors;
    QString stamp = localCatalogMetadataStamp(catalogue);
    const bool watching = mode != QStringLiteral("none");
    bool identityAvailable = false;
#ifdef Q_OS_WIN
    identityAvailable = !localCatalogWindowsIdentity(QFileInfo(catalogue)).isEmpty();
#endif
    QElapsedTimer elapsed;
    elapsed.start();
    {
        // These objects outlive the writer; no catalogue-content reader runs in
        // a callback. Store readers/writers use only their production QLockFile.
        QEventLoop loop;
        QFileSystemWatcher watcher;
        const auto arm = [&]() {
            if (mode == QStringLiteral("file-and-directory")) {
                watchLocalCatalog(watcher, catalogue); // Actual frozen model helper.
            } else if (mode == QStringLiteral("directory-only-fileid")) {
                const QString parent = QFileInfo(catalogue).absolutePath();
                if (!watcher.directories().contains(parent)) {
                    require(watcher.addPath(parent), "Cannot arm the parent-directory watcher");
                }
            }
            ++rearms;
        };
        const auto metadataEvent = [&]() {
            if (inMutation.load()) { ++callbacksDuringMutation; }
            const QString latest = localCatalogMetadataStamp(catalogue);
            if (latest != stamp) { ++stampChanges; stamp = latest; }
        };
        QObject::connect(&watcher, &QFileSystemWatcher::fileChanged, &loop, [&](const QString&) {
            ++fileEvents;
            arm(); // Mirrors LocalScoresModel's native-file rearming path.
            metadataEvent();
        });
        QObject::connect(&watcher, &QFileSystemWatcher::directoryChanged, &loop, [&](const QString&) {
            ++directoryEvents;
            metadataEvent();
        });
        if (watching) {
            arm();
            require(watcher.directories().size() == 1, "Parent watch was not actually installed");
            require(watcher.files().size() == (mode == QStringLiteral("file-and-directory") ? 1 : 0), "Unexpected native file watch mode");
        }
        QTimer completion;
        completion.setInterval(5);
        QObject::connect(&completion, &QTimer::timeout, &loop, [&]() { if (done.load()) { loop.quit(); } });
        completion.start();
        std::thread writer([&]() {
            try {
                LocalScoreLibraryStore store(catalogue);
                const auto until = std::chrono::steady_clock::now() + std::chrono::milliseconds(budgetMs);
                for (int index = 0; index < iterations; ++index) {
                    if (std::chrono::steady_clock::now() >= until) { budgetReached = true; break; }
                    const bool enable = index % 16 == 0;
                    const bool favorite = (index & 1) != 0;
                    inMutation = true;
                    const auto result = enable ? store.enableCollections() : store.setFavorite(entryId, favorite);
                    inMutation = false;
                    ++attempts;
                    if (enable) { ++enableAttempts; }
                    if (result.ok) {
                        ++successes;
                        if (enable) { ++enableSuccesses; expectedSchema = 2; }
                        else { expectedFavorite = favorite; }
                    } else {
                        ++failures;
                        if (errors.size() < 12) {
                            errors.append(QJsonObject { { "iteration", index }, { "operation", enable ? "enable-collections" : "favorite" },
                                                        { "error", result.error } });
                        }
                    }
                }
            } catch (const std::exception& error) {
                ++failures; errors.append(QJsonObject { { "fatal_writer_exception", QString::fromUtf8(error.what()) } });
            } catch (...) {
                ++failures; errors.append(QJsonObject { { "fatal_writer_exception", "unknown" } });
            }
            inMutation = false;
            done = true;
        });
        loop.exec(); // The event dispatcher remains live throughout worker mutations.
        writer.join();
        // No manual processEvents between individual mutations. In particular,
        // native PathInfo refreshes and GUI callbacks can overlap QSaveFile.
        completion.stop();
    } // Destroy/join the native watcher before reading any result catalogue bytes.

    const auto after = initial.load();
    const bool preserved = after.ok && after.entries.size() == 1 && after.entries[0].id == entryId
                           && after.entries[0].path == scorePath && after.entries[0].favorite == expectedFavorite
                           && after.schemaVersion == expectedSchema && after.collections.isEmpty()
                           && hash(scorePath) == originalHash;
    const QJsonObject report {
        { "location_group", location }, { "location", locationInfo }, { "mode", mode }, { "round", round }, { "iterations_requested", iterations }, { "attempts", attempts },
        { "successes", successes }, { "failures", failures }, { "enable_attempts", enableAttempts }, { "enable_successes", enableSuccesses },
        { "budget_ms", budgetMs }, { "budget_reached", budgetReached }, { "elapsed_ms", elapsed.elapsed() },
        { "file_events", fileEvents }, { "directory_events", directoryEvents }, { "stamp_changes", stampChanges },
        { "callbacks_overlapping_store_mutation", callbacksDuringMutation }, { "rearm_calls", rearms },
        { "native_parent_fileid_available", identityAvailable }, { "final_catalogue_valid", after.ok },
        { "expected_final_schema", expectedSchema }, { "expected_final_favorite", expectedFavorite },
        { "data_preserved", preserved }, { "original_score_sha256", QString::fromLatin1(originalHash) }, { "errors", errors }
    };
    return { report, failures, preserved, callbacksDuringMutation };
}
}
int main(int argc, char** argv)
{
    QCoreApplication application(argc, argv);
    if (application.arguments().size() != 2) {
        std::cerr << "Exactly one new diagnostic output path is required.\n";
        return 2;
    }
    const QString output = application.arguments()[1];
    if (QFileInfo::exists(output)) { std::cerr << "Existing report refused.\n"; return 2; }
    try {
        QJsonArray phases;
        int noWatchFailures = 0, fileWatchFailures = 0, directoryOnlyFailures = 0, overlap = 0;
        bool preserved = true;
        const auto runLocation = [&](const QString& location, const QString& baseRoot) {
            for (int round = 0; round < 2; ++round) {
                const QStringList order = round == 0 ? QStringList { "none", "file-and-directory", "directory-only-fileid" }
                                                    : QStringList { "directory-only-fileid", "file-and-directory", "none" };
                for (const QString& mode : order) {
                    const auto phase = runPhase(location, baseRoot, mode, round, 2000, 30000);
                    phases.append(phase.report);
                    preserved = preserved && phase.preservation;
                    overlap += phase.overlappedCallbacks;
                    if (mode == "none") { noWatchFailures += phase.failures; }
                    else if (mode == "file-and-directory") { fileWatchFailures += phase.failures; }
                    else { directoryOnlyFailures += phase.failures; }
                    std::cout << "OBSERVATION " << QJsonDocument(phase.report).toJson(QJsonDocument::Compact).constData() << '\n';
                }
            }
        };
        const QString defaultRoot = QDir::tempPath();
        runLocation(QStringLiteral("default-temp"), defaultRoot);
        bool localExperimentPerformed = false;
        QString localRoot;
#ifdef Q_OS_WIN
        // A clear Temp comparison may miss the C: profile-volume behavior of
        // the actual GUI. Use a new owned child of LocalAppData, never Cadence's
        // existing application/organisation directories or configuration.
        if (!noWatchFailures && !fileWatchFailures && !directoryOnlyFailures) {
            localRoot = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
            require(!localRoot.isEmpty() && QDir(localRoot).exists(), "Known-Folder LocalAppData root is unavailable");
            localExperimentPerformed = true;
            runLocation(QStringLiteral("fresh-local-appdata"), localRoot);
        }
#endif
#ifdef Q_OS_WIN
        const bool nativeWindows = true;
#else
        const bool nativeWindows = false;
#endif
        const bool selectiveConflict = nativeWindows && !noWatchFailures && fileWatchFailures > 0
                                       && !directoryOnlyFailures && overlap > 0 && preserved;
        const QJsonObject report {
            { "schema_version", 1 }, { "qt_version", qVersion() }, { "native_windows", nativeWindows },
            { "default_temp_root", defaultRoot }, { "local_appdata_root", localRoot },
            { "fresh_local_appdata_experiment_performed", localExperimentPerformed },
            { "existing_cadence_profiles_accessed", false },
            { "source_commit", "961c80b235d413dc9d123ea8f669ddb7f84ecd09" },
            { "no_watch_failures", noWatchFailures }, { "file_and_directory_failures", fileWatchFailures },
            { "directory_only_failures", directoryOnlyFailures }, { "data_preserved", preserved },
            { "callbacks_overlapping_mutations", overlap }, { "selective_file_watch_conflict_observed", selectiveConflict },
            { "interpretation", selectiveConflict ? "file-watch conflicts observed; directory-only control clear in this bounded experiment"
                    : !nativeWindows ? "Linux compile/runtime smoke only; no Windows causal conclusion"
                    : "no selective causal result; inspect controls/errors, do not infer a GUI fix" },
            { "application_built", false }, { "gui_tested", false }, { "catalogue_reads_in_callbacks", false }, { "phases", phases }
        };
        QSaveFile file(output);
        file.setDirectWriteFallback(false);
        const auto bytes = QJsonDocument(report).toJson(QJsonDocument::Indented);
        require(file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit(), "Cannot save diagnostic report");
        std::cout << "RESULT " << QJsonDocument(report).toJson(QJsonDocument::Compact).constData() << '\n';
        return preserved && !noWatchFailures ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << "DIAGNOSTIC_FAILURE: " << error.what() << '\n';
        return 1;
    }
}
