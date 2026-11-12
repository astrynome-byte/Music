// SPDX-License-Identifier: GPL-3.0-only
// Future native Windows CI harness. Loads a reviewed DLL directly, no registry.
#include "qa_clock_api.h"
#include "qa_environment.h"
#include <atomic>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>

namespace {
struct Context {
    IASIO* driver = nullptr;
    ASIOBufferInfo* buffers = nullptr;
    bool silence = false, timeInfo = false, stopInCallback = false;
    std::atomic<unsigned> calls {0}, errors {0};
};
std::atomic<Context*> current {nullptr};
HMODULE reviewedModule = nullptr;
void require(bool condition, const char* text) { if (!condition) { throw std::runtime_error(text); } }
void switched(long half, ASIOBool direct) {
    auto* context = current.load(); if (!context) { return; }
    if ((half != 0 && half != 1) || direct != ASIOTrue) { ++context->errors; return; }
    ASIOSamples samples {}; ASIOTimeStamp timestamp {};
    if (context->driver->getSamplePosition(&samples, &timestamp) != ASE_OK) { ++context->errors; }
    const unsigned count = context->calls++;
    const std::uint64_t frame = (static_cast<std::uint64_t>(samples.hi) << 32) | samples.lo;
    if (frame != static_cast<std::uint64_t>(count) * QaFramesPerBlock) { ++context->errors; }
    for (long channel = 0; channel < QaOutputChannels; ++channel) {
        auto* output = static_cast<float*>(context->buffers[channel].buffers[half]);
        for (long i = 0; i < QaFramesPerBlock; ++i) { output[i] = context->silence ? 0.0f : (i % 2 ? -1.0f : 1.0f) * (channel ? .5f : .25f); }
    }
    if (context->stopInCallback && context->driver->stop() != ASE_InvalidMode) { ++context->errors; }
}
ASIOTime* switchedTime(ASIOTime* time, long half, ASIOBool direct) {
    auto* context = current.load();
    if (!time || !context || !context->timeInfo || !(time->timeInfo.flags & kSamplePositionValid)) {
        if (context) { ++context->errors; } return time;
    }
    switched(half, direct); return time;
}
void rateChanged(ASIOSampleRate) { if (auto* context = current.load()) { ++context->errors; } }
long messages(long selector, long, void*, double*) {
    if (selector == kAsioEngineVersion) { return 2; }
    auto* context = current.load();
    return selector == kAsioSupportsTimeInfo && context && context->timeInfo ? 1 : 0;
}
class Instance {
public:
    IASIO* driver = nullptr; ICadenceQaClockStats* statistics = nullptr;
    explicit Instance(IClassFactory* factory) {
        const HRESULT created = factory
            ? factory->CreateInstance(nullptr, CLSID_CadenceQaClock, reinterpret_cast<void**>(&driver))
            : CoCreateInstance(CLSID_CadenceQaClock, nullptr, CLSCTX_INPROC_SERVER, CLSID_CadenceQaClock, reinterpret_cast<void**>(&driver));
        require(SUCCEEDED(created), "CreateInstance/CoCreateInstance failed");
        // COM can resolve HKCU before HKLM. Verify the created IASIO vtable's
        // implementation belongs to the explicitly loaded reviewed DLL too.
        auto** table = *reinterpret_cast<void***>(driver);
        MEMORY_BASIC_INFORMATION mapping {};
        if (!VirtualQuery(table[0], &mapping, sizeof(mapping)) || mapping.AllocationBase != reviewedModule) {
            driver->Release(); driver = nullptr; throw std::runtime_error("Created COM interface belongs to another module");
        }
        if (FAILED(driver->QueryInterface(IID_ICadenceQaClockStats, reinterpret_cast<void**>(&statistics)))) { driver->Release(); driver = nullptr; throw std::runtime_error("Stats QI failed"); }
    }
    ~Instance() { if (driver) { driver->stop(); driver->disposeBuffers(); } if (statistics) { statistics->Release(); } if (driver) { driver->Release(); } }
};
void scenario(IClassFactory* factory, double rate, bool silence, bool timeInfo, bool stopInCallback) {
    Instance instance(factory);
    require(instance.driver->init(nullptr) == ASIOTrue, "init failed");
    require(instance.driver->canSampleRate(96000) == ASE_NoClock, "unsupported rate accepted");
    require(instance.driver->setSampleRate(rate) == ASE_OK, "setSampleRate failed");
    long inputs = -1, outputs = -1;
    require(instance.driver->getChannels(&inputs, &outputs) == ASE_OK && !inputs && outputs == 2, "channel contract differs");
    ASIOBufferInfo buffers[2] {{ASIOFalse, 0, {nullptr,nullptr}}, {ASIOFalse, 1, {nullptr,nullptr}}};
    Context context; context.driver = instance.driver; context.buffers = buffers; context.silence = silence;
    context.timeInfo = timeInfo; context.stopInCallback = stopInCallback; current = &context;
    ASIOCallbacks callbacks {switched, rateChanged, messages, switchedTime};
    try {
        require(instance.driver->createBuffers(buffers, 2, 128, &callbacks) != ASE_OK, "unsupported block accepted");
        require(instance.driver->createBuffers(buffers, 2, QaFramesPerBlock, &callbacks) == ASE_OK, "createBuffers failed");
        require(instance.driver->createBuffers(buffers, 2, QaFramesPerBlock, &callbacks) != ASE_OK, "duplicate allocation accepted");
        require(instance.driver->start() == ASE_OK, "start failed");
        require(instance.driver->start() == ASE_InvalidMode, "duplicate start accepted");
        require(instance.driver->setSampleRate(rate) == ASE_InvalidMode, "rate change while active accepted");
        Sleep(stopInCallback ? 60 : 180);
        require(instance.driver->stop() == ASE_OK, "stop/drain failed");
        const auto stoppedCalls = context.calls.load(); Sleep(30);
        require(context.calls == stoppedCalls && !context.errors, "callback continued after stop or callback contract failed");
        QaClockStats statistics;
        require(SUCCEEDED(instance.statistics->GetStoppedStats(&statistics, sizeof(statistics))), "GetStoppedStats failed");
        require(statistics.callbacks >= 1 && statistics.callbacks == stoppedCalls && statistics.frames == statistics.callbacks * QaFramesPerBlock, "callback/frame counters differ");
        require(statistics.sampleRate == rate && statistics.activeChannels == 2 && statistics.reportWritten == 1, "report/format absent");
        require(statistics.finiteSamples == statistics.frames * 2 && !statistics.nonfiniteSamples && !statistics.clippedSamples && !statistics.callbackErrors, "invalid sample metrics");
        require(silence ? statistics.nonzeroSamples == 0 && statistics.peak == 0 && statistics.rms == 0
                        : statistics.nonzeroSamples == statistics.finiteSamples && statistics.peak == .5 && std::abs(statistics.rms - std::sqrt(.15625)) < 1e-10, "host PCM not measured after callback");
        std::printf("PASS rate=%.0f time_info=%s silence=%s self_stop=%s callbacks=%llu frames=%llu peak=%.9g rms=%.9g\n", rate,
                    timeInfo ? "true":"false", silence ? "true":"false", stopInCallback ? "true":"false",
                    static_cast<unsigned long long>(statistics.callbacks), static_cast<unsigned long long>(statistics.frames), statistics.peak, statistics.rms);
        require(instance.driver->disposeBuffers() == ASE_OK, "dispose failed");
        current = nullptr;
    } catch (...) { instance.driver->stop(); current = nullptr; throw; }
}
}
int wmain(int count, wchar_t** values) {
    const bool registered = count == 3 && std::wstring(values[2]) == L"--registered";
    if ((count != 2 && !registered) || !cadence::qa::disposableCi()
        || (registered && cadence::qa::environment(L"CADENCE_QA_CLOCK_REGISTRY_SCOPE").empty())) {
        std::fputs("REFUSED: disposable Windows x64 CI and reviewed DLL path required; registered mode also requires an explicit owned scope.\n", stderr); return 2;
    }
    const HRESULT com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(com)) { return 3; }
    HMODULE module = LoadLibraryExW(values[1], nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!module) { CoUninitialize(); return 4; }
    reviewedModule = module;
    using GetFactory = HRESULT (__stdcall *)(REFCLSID, REFIID, void**);
    using CanUnload = HRESULT (__stdcall *)();
    auto getFactory = reinterpret_cast<GetFactory>(GetProcAddress(module, "DllGetClassObject"));
    auto canUnload = reinterpret_cast<CanUnload>(GetProcAddress(module, "DllCanUnloadNow"));
    IClassFactory* factory = nullptr; int result = 1;
    try {
        require(getFactory && canUnload, "COM exports absent");
        if (!registered) {
            require(SUCCEEDED(getFactory(CLSID_CadenceQaClock, IID_IClassFactory, reinterpret_cast<void**>(&factory))), "factory export rejected");
            require(canUnload() == S_FALSE, "live factory did not hold DLL busy");
        }
        scenario(factory, 44100, false, false, false);
        scenario(factory, 48000, false, true, false);
        scenario(factory, 48000, true, false, false);
        scenario(factory, 44100, false, true, true);
        if (factory) { factory->Release(); factory = nullptr; }
        require(canUnload() == S_OK, "objects or workers not drained");
        std::printf("PASS 4 native ASIO ABI scenarios through %s; no physical output or listening.\n",
                    registered ? "CoCreateInstance inside explicit owned registry scope" : "direct DllGetClassObject without registry");
        result = 0;
    } catch (const std::exception& error) { std::fprintf(stderr, "FAIL: %s\n", error.what()); }
    if (factory) { factory->Release(); }
    if (!canUnload || canUnload() == S_OK) { FreeLibrary(module); }
    CoUninitialize(); return result;
}
