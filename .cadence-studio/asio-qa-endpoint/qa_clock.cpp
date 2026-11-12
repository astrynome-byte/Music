// SPDX-License-Identifier: GPL-3.0-only
// Independently implemented QA sink. No sample COM helpers or physical audio I/O.
#include "qa_clock_api.h"
#include "qa_environment.h"
#include "sample_metrics.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <new>
#include <vector>
#include <locale.h>

namespace {
std::atomic<unsigned long> liveObjects {0}, serverLocks {0}, liveWorkers {0};
class QaClock;
thread_local QaClock* activeClock = nullptr;
using Clock = std::chrono::steady_clock;
// The pinned SDK deliberately defines two distinct hi/lo structure types:
// ASIOSamples and ASIOTimeStamp. Write their words without pointer casting.
template <typename WordPair>
void pairValue(std::uint64_t value, WordPair* result) noexcept {
    result->hi = static_cast<unsigned long>(value >> 32);
    result->lo = static_cast<unsigned long>(value & 0xffffffffULL);
}

class QaClock final : public IASIO, public ICadenceQaClockStats {
public:
    QaClock() { ++liveObjects; }
    ~QaClock() {
        // The worker owns an object reference and a module reference. On its last
        // Release it has already finished all callbacks/statistics before deletion.
        if (onWorker()) {
            if (worker) { CloseHandle(worker); worker = nullptr; }
        } else { std::lock_guard<std::mutex> guard(control); stopControlled(); }
        if (stopEvent) { CloseHandle(stopEvent); }
        if (paceTimer) { CloseHandle(paceTimer); }
        --liveObjects;
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) { return E_POINTER; }
        *output = nullptr;
        if (IsEqualIID(iid, IID_IUnknown) || IsEqualIID(iid, CLSID_CadenceQaClock)) { *output = static_cast<IASIO*>(this); }
        else if (IsEqualIID(iid, IID_ICadenceQaClockStats)) { *output = static_cast<ICadenceQaClockStats*>(this); }
        else { return E_NOINTERFACE; }
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references; }
    ULONG STDMETHODCALLTYPE Release() override { const ULONG remaining = --references; if (!remaining) { delete this; } return remaining; }

    // A host can Release its last reference reentrantly from a callback.
    // Keep lifecycle calls alive through unlocking their control mutex.
    struct CallReference {
        QaClock* clock;
        explicit CallReference(QaClock* value) : clock(value) { clock->AddRef(); }
        ~CallReference() { clock->Release(); }
    };

    ASIOBool init(void*) override {
        if (onWorker() || configuring.load()) { return ASIOFalse; }
        std::lock_guard<std::mutex> guard(control);
        if (initialized) { return ASIOTrue; }
        if (!cadence::qa::disposableCi(&statsDirectory)) { return ASIOFalse; }
        if (FAILED(CoCreateGuid(&instanceId))) { return ASIOFalse; }
        stopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (!stopEvent) { return ASIOFalse; }
        paceTimer = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_MODIFY_STATE | SYNCHRONIZE);
        if (!paceTimer) { CloseHandle(stopEvent); stopEvent = nullptr; return ASIOFalse; }
        initialized = true; return ASIOTrue;
    }
    void getDriverName(char* name) override { if (name) { std::strcpy(name, "Cadence QA Clock (silent sink)"); } }
    long getDriverVersion() override { return 1; }
    void getErrorMessage(char* text) override { if (text) { std::strcpy(text, "QA-only silent sink; no physical audio output"); } }
    ASIOError start() override {
        CallReference keepAlive(this);
        if (onWorker() || configuring.load()) { return ASE_InvalidMode; }
        std::lock_guard<std::mutex> guard(control);
        if (!initialized || !prepared || worker) { return ASE_InvalidMode; }
        metrics = {}; callbackCount = frames = lateBlocks = callbackErrors = 0;
        ++positionSequence; position = timestamp = 0; ++positionSequence;
        reportWritten = false; ++generation;
        runRate = sampleRate; runChannels = activeChannels;
        for (auto& channel : buffers) { std::fill(channel.begin(), channel.end(), 0.0f); }
        ResetEvent(stopEvent);
        // Keep the module loaded through the final return of the worker, even if
        // a client releases every COM reference while a callback is in flight.
        HMODULE module = nullptr;
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
            reinterpret_cast<LPCWSTR>(&threadEntry), &module)) { return ASE_HWMalfunction; }
        workerModule = module; AddRef(); ++liveWorkers; running = true;
        worker = CreateThread(nullptr, 0, &threadEntry, this, 0, nullptr);
        if (!worker) { running = false; --liveWorkers; Release(); FreeLibrary(module); workerModule = nullptr; return ASE_HWMalfunction; }
        return ASE_OK;
    }
    ASIOError stop() override {
        CallReference keepAlive(this);
        if (configuring.load()) { return ASE_InvalidMode; }
        if (onWorker()) { if (stopEvent) { SetEvent(stopEvent); } return ASE_InvalidMode; }
        std::lock_guard<std::mutex> guard(control);
        return stopControlled();
    }
    ASIOError getChannels(long* inputs, long* outputs) override {
        if (!inputs || !outputs) { return ASE_InvalidParameter; }
        *inputs = 0; *outputs = QaOutputChannels; return ASE_OK;
    }
    ASIOError getLatencies(long* input, long* output) override {
        if (!input || !output) { return ASE_InvalidParameter; }
        *input = 0; *output = QaFramesPerBlock; return ASE_OK;
    }
    ASIOError getBufferSize(long* minimum, long* maximum, long* preferred, long* granularity) override {
        if (!minimum || !maximum || !preferred || !granularity) { return ASE_InvalidParameter; }
        *minimum = *maximum = *preferred = QaFramesPerBlock; *granularity = 0; return ASE_OK;
    }
    ASIOError canSampleRate(ASIOSampleRate value) override { return value == 44100 || value == 48000 ? ASE_OK : ASE_NoClock; }
    ASIOError getSampleRate(ASIOSampleRate* value) override { if (!value) { return ASE_InvalidParameter; } *value = sampleRate; return ASE_OK; }
    ASIOError setSampleRate(ASIOSampleRate value) override {
        if (canSampleRate(value) != ASE_OK) { return ASE_NoClock; }
        if (onWorker() || configuring.load()) { return ASE_InvalidMode; }
        std::lock_guard<std::mutex> guard(control);
        if (worker) { return ASE_InvalidMode; }
        sampleRate = value; return ASE_OK;
    }
    ASIOError getClockSources(ASIOClockSource* clocks, long* count) override {
        if (!clocks || !count || *count < 1) { return ASE_InvalidParameter; }
        *count = 1; clocks[0] = {}; clocks[0].index = 0; clocks[0].associatedChannel = clocks[0].associatedGroup = -1;
        clocks[0].isCurrentSource = ASIOTrue; std::strcpy(clocks[0].name, "QA steady clock (not hardware)"); return ASE_OK;
    }
    ASIOError setClockSource(long index) override { return index == 0 ? ASE_OK : ASE_InvalidParameter; }
    ASIOError getSamplePosition(ASIOSamples* samples, ASIOTimeStamp* time) override {
        if (!samples || !time) { return ASE_InvalidParameter; }
        std::uint64_t frameValue, timeValue, sequence;
        do {
            sequence = positionSequence.load();
            if (sequence & 1U) { continue; }
            frameValue = position.load(); timeValue = timestamp.load();
        } while ((sequence & 1U) || sequence != positionSequence.load());
        pairValue(frameValue, samples); pairValue(timeValue, time); return ASE_OK;
    }
    ASIOError getChannelInfo(ASIOChannelInfo* info) override {
        if (!info || info->isInput || info->channel < 0 || info->channel >= QaOutputChannels) { return ASE_InvalidParameter; }
        info->isActive = (activeMask.load() & (1U << info->channel)) ? ASIOTrue : ASIOFalse;
        info->type = ASIOSTFloat32LSB; info->channelGroup = 0;
        std::strcpy(info->name, info->channel ? "QA sink right (no speaker)" : "QA sink left (no speaker)"); return ASE_OK;
    }
    ASIOError createBuffers(ASIOBufferInfo* infos, long count, long size, ASIOCallbacks* host) override {
        CallReference keepAlive(this);
        if (onWorker() || configuring.load()) { return ASE_InvalidMode; }
        std::lock_guard<std::mutex> guard(control);
        if (!initialized || worker || prepared || !infos || !host || !host->bufferSwitch || !host->asioMessage
            || size != QaFramesPerBlock || count < 1 || count > QaOutputChannels) { return ASE_InvalidParameter; }
        unsigned mask = 0;
        for (long index = 0; index < count; ++index) {
            const auto& info = infos[index];
            if (info.isInput || info.channelNum < 0 || info.channelNum >= QaOutputChannels
                || (mask & (1U << info.channelNum))) { return ASE_InvalidParameter; }
            mask |= 1U << info.channelNum;
        }
        try { for (auto& channel : buffers) { channel.assign(2 * QaFramesPerBlock, 0.0f); } }
        catch (const std::bad_alloc&) { for (auto& channel : buffers) { channel.clear(); } return ASE_NoMemory; }
        callbacks = *host;
        // Do not deadlock if a host reenters lifecycle control while answering
        // its synchronous capability query. Read-only queries remain available.
        configuring = true;
        try { useTimeInfo = host->bufferSwitchTimeInfo && host->asioMessage(kAsioSupportsTimeInfo, 0, nullptr, nullptr) == 1; }
        catch (...) { configuring = false; callbacks = {}; for (auto& channel : buffers) { channel.clear(); } return ASE_HWMalfunction; }
        configuring = false;
        for (long index = 0; index < count; ++index) {
            infos[index].buffers[0] = buffers[infos[index].channelNum].data();
            infos[index].buffers[1] = buffers[infos[index].channelNum].data() + QaFramesPerBlock;
        }
        activeMask = mask; activeChannels = static_cast<unsigned>(count); prepared = true; return ASE_OK;
    }
    ASIOError disposeBuffers() override {
        CallReference keepAlive(this);
        if (configuring.load()) { return ASE_InvalidMode; }
        if (onWorker()) { if (stopEvent) { SetEvent(stopEvent); } return ASE_InvalidMode; }
        std::lock_guard<std::mutex> guard(control);
        const auto result = stopControlled(); if (result != ASE_OK) { return result; }
        for (auto& channel : buffers) { channel.clear(); }
        callbacks = {}; activeMask = 0; activeChannels = 0; prepared = false; return ASE_OK;
    }
    ASIOError controlPanel() override { return ASE_NotPresent; }
    ASIOError future(long selector, void*) override { return selector == kAsioCanTimeInfo ? ASE_SUCCESS : ASE_InvalidParameter; }
    ASIOError outputReady() override { return ASE_NotPresent; }
    HRESULT STDMETHODCALLTYPE GetStoppedStats(QaClockStats* output, std::uint32_t bytes) override {
        if (!output || bytes != sizeof(QaClockStats)) { return E_INVALIDARG; }
        if (onWorker() || running.load() || configuring.load()) { return E_PENDING; }
        std::lock_guard<std::mutex> guard(control);
        if (running.load()) { return E_PENDING; }
        *output = snapshot(); return S_OK;
    }
private:
    bool onWorker() const { return activeClock == this; }
    // Caller holds control across drain and the following lifecycle mutation.
    // This excludes a start between stop and disposal of its buffers/callbacks.
    ASIOError stopControlled() {
        if (worker) {
            SetEvent(stopEvent);
            // Never free buffers/unload while a host callback is in progress.
            // The separate CI process has a timeout if the host callback hangs.
            if (WaitForSingleObject(worker, INFINITE) != WAIT_OBJECT_0) { return ASE_HWMalfunction; }
            CloseHandle(worker); worker = nullptr; workerModule = nullptr;
        }
        return ASE_OK;
    }
    QaClockStats snapshot() const {
        QaClockStats result;
        result.callbacks = callbackCount; result.frames = frames; result.finiteSamples = metrics.finiteSamples;
        result.nonzeroSamples = metrics.nonzeroSamples; result.nonfiniteSamples = metrics.nonfiniteSamples;
        result.clippedSamples = metrics.clippedSamples; result.lateBlocks = lateBlocks; result.callbackErrors = callbackErrors;
        result.sampleRate = runRate; result.peak = metrics.peak; result.rms = metrics.rms();
        result.activeChannels = runChannels; result.reportWritten = reportWritten ? 1U : 0U; return result;
    }
    void writeReport() noexcept {
        wchar_t identity[40] {}; if (!StringFromGUID2(instanceId, identity, 40)) { return; }
        wchar_t path[32768] {};
        if (_snwprintf_s(path, _countof(path), _TRUNCATE, L"%ls\\clock-%ls-%u.json", statsDirectory.c_str(), identity, generation) < 0) { return; }
        const auto stats = snapshot();
        char json[4096] {};
        _locale_t numericLocale = _create_locale(LC_NUMERIC, "C");
        if (!numericLocale) { return; }
        const int length = _snprintf_l(json, sizeof(json),
            "{\"schema_version\":1,\"endpoint\":\"Cadence QA Clock (silent sink)\",\"physical_audio_output\":false,"
            "\"qualified_hardware\":false,\"callbacks\":%llu,\"frames\":%llu,\"finite_samples\":%llu,"
            "\"nonzero_samples\":%llu,\"nonfinite_samples\":%llu,\"clipped_samples\":%llu,\"late_blocks\":%llu,"
            "\"callback_errors\":%llu,\"sample_rate\":%.0f,\"active_channels\":%u,\"peak\":%.17g,\"rms\":%.17g}\n", numericLocale,
            static_cast<unsigned long long>(stats.callbacks), static_cast<unsigned long long>(stats.frames),
            static_cast<unsigned long long>(stats.finiteSamples), static_cast<unsigned long long>(stats.nonzeroSamples),
            static_cast<unsigned long long>(stats.nonfiniteSamples), static_cast<unsigned long long>(stats.clippedSamples),
            static_cast<unsigned long long>(stats.lateBlocks), static_cast<unsigned long long>(stats.callbackErrors),
            stats.sampleRate, stats.activeChannels, stats.peak, stats.rms);
        _free_locale(numericLocale);
        if (length <= 0 || length >= static_cast<int>(sizeof(json))) { return; }
        HANDLE file = CreateFileW(path, GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE) { return; }
        DWORD written = 0;
        const bool success = WriteFile(file, json, static_cast<DWORD>(length), &written, nullptr)
            && written == static_cast<DWORD>(length) && FlushFileBuffers(file);
        CloseHandle(file); if (success) { reportWritten = true; } else { DeleteFileW(path); }
    }
    void run() noexcept {
        const double rate = runRate;
        const auto period = std::chrono::nanoseconds(static_cast<long long>(1e9 * QaFramesPerBlock / rate));
        const auto beginning = Clock::now(); auto next = beginning; long toggle = 0;
        while (WaitForSingleObject(stopEvent, 0) == WAIT_TIMEOUT
               && Clock::now() - beginning < std::chrono::seconds(QaMaximumRunSeconds)) {
            ++positionSequence; position = frames;
            timestamp = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
            ++positionSequence;
            try {
                // A callback that writes nothing must measure as silence, never
                // as stale PCM retained from the preceding visit to this half.
                for (unsigned channel = 0; channel < QaOutputChannels; ++channel) {
                    if (activeMask.load() & (1U << channel)) {
                        auto first = buffers[channel].begin() + toggle * QaFramesPerBlock;
                        std::fill(first, first + QaFramesPerBlock, 0.0f);
                    }
                }
                if (useTimeInfo) {
                    ASIOTime time {}; time.timeInfo.speed = 1; time.timeInfo.sampleRate = rate;
                    time.timeInfo.flags = kSystemTimeValid | kSamplePositionValid | kSampleRateValid | kSpeedValid;
                    pairValue(position, &time.timeInfo.samplePosition); pairValue(timestamp, &time.timeInfo.systemTime);
                    callbacks.bufferSwitchTimeInfo(&time, toggle, ASIOTrue);
                } else { callbacks.bufferSwitch(toggle, ASIOTrue); }
                ++callbackCount;
                // The host has just filled this half. Inspect only those output samples.
                const unsigned mask = activeMask;
                for (unsigned channel = 0; channel < QaOutputChannels; ++channel) {
                    if (!(mask & (1U << channel))) { continue; }
                    for (long frame = 0; frame < QaFramesPerBlock; ++frame) { metrics.add(buffers[channel][toggle * QaFramesPerBlock + frame]); }
                }
                frames += QaFramesPerBlock;
            } catch (...) { ++callbackErrors; SetEvent(stopEvent); }
            toggle ^= 1; next += period;
            const auto now = Clock::now();
            if (now > next + period) { ++lateBlocks; next = now + period; }
            if (next > now) {
                const auto remaining = std::chrono::duration_cast<std::chrono::nanoseconds>(next - now).count();
                LARGE_INTEGER due {}; due.QuadPart = -((remaining + 99) / 100);
                if (!SetWaitableTimerEx(paceTimer, &due, 0, nullptr, nullptr, nullptr, 0)) { ++callbackErrors; break; }
                HANDLE waits[2] {stopEvent, paceTimer};
                const DWORD waited = WaitForMultipleObjects(2, waits, FALSE, INFINITE);
                if (waited != WAIT_OBJECT_0 && waited != WAIT_OBJECT_0 + 1) { ++callbackErrors; break; }
            }
        }
        CancelWaitableTimer(paceTimer);
        writeReport(); running = false;
    }
    static DWORD WINAPI threadEntry(void* context) {
        auto* clock = static_cast<QaClock*>(context); HMODULE module = clock->workerModule;
        activeClock = clock;
        clock->run(); clock->Release(); activeClock = nullptr; --liveWorkers;
        FreeLibraryAndExitThread(module, 0);
    }
    std::atomic<ULONG> references {1};
    std::mutex control;
    HANDLE stopEvent = nullptr, worker = nullptr, paceTimer = nullptr; HMODULE workerModule = nullptr;
    std::atomic<bool> running {false};
    std::atomic<bool> configuring {false};
    bool initialized = false, prepared = false, useTimeInfo = false, reportWritten = false;
    std::atomic<double> sampleRate {48000};
    std::atomic<unsigned> activeMask {0}; unsigned activeChannels = 0, generation = 0;
    double runRate = 0; unsigned runChannels = 0;
    std::atomic<std::uint64_t> position {0}, timestamp {0}, positionSequence {0};
    std::uint64_t callbackCount = 0, frames = 0, lateBlocks = 0, callbackErrors = 0;
    cadence::qa::SampleMetrics metrics;
    std::array<std::vector<float>, QaOutputChannels> buffers;
    ASIOCallbacks callbacks {};
    std::wstring statsDirectory; GUID instanceId {};
};

class Factory final : public IClassFactory {
public:
    Factory() { ++liveObjects; } ~Factory() { --liveObjects; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) { return E_POINTER; } *output = nullptr;
        if (!IsEqualIID(iid, IID_IUnknown) && !IsEqualIID(iid, IID_IClassFactory)) { return E_NOINTERFACE; }
        *output = static_cast<IClassFactory*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references; }
    ULONG STDMETHODCALLTYPE Release() override { const auto left = --references; if (!left) { delete this; } return left; }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID iid, void** output) override {
        if (!output) { return E_POINTER; } *output = nullptr;
        if (outer) { return CLASS_E_NOAGGREGATION; }
        if (!cadence::qa::disposableCi()) { return E_ACCESSDENIED; }
        auto* clock = new (std::nothrow) QaClock;
        if (!clock) { return E_OUTOFMEMORY; }
        const auto result = clock->QueryInterface(iid, output); clock->Release(); return result;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override {
        if (lock) { ++serverLocks; return S_OK; }
        auto current = serverLocks.load();
        while (current && !serverLocks.compare_exchange_weak(current, current - 1)) {}
        return current ? S_OK : E_UNEXPECTED;
    }
private: std::atomic<ULONG> references {1};
};
}

extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid, REFIID iid, void** output) {
    if (!output) { return E_POINTER; } *output = nullptr;
    if (!IsEqualCLSID(clsid, CLSID_CadenceQaClock)) { return CLASS_E_CLASSNOTAVAILABLE; }
    auto* factory = new (std::nothrow) Factory;
    if (!factory) { return E_OUTOFMEMORY; }
    const auto result = factory->QueryInterface(iid, output); factory->Release(); return result;
}
extern "C" HRESULT __stdcall DllCanUnloadNow() { return !liveObjects && !liveWorkers && !serverLocks ? S_OK : S_FALSE; }
