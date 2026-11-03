// SPDX-License-Identifier: GPL-3.0-only
// Independent probe, not integrated into Cadence or its AbstractAudioEncoder.
#include <windows.h>
#include <mfapi.h>
#include <mferror.h>
#include <mfidl.h>
#include <mftransform.h>
#include <wmcodecdsp.h>
#include <wrl/client.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
namespace fs = std::filesystem;

#if !defined(_M_X64)
#error "This probe targets Windows x64 only."
#endif

namespace {
constexpr UINT32 channels = 2;
constexpr UINT32 blockFrames = 1024;
constexpr UINT32 bytesPerFrame = channels * sizeof(int16_t);
constexpr uint64_t ticksPerSecond = 10000000;

std::string hrText(HRESULT hr)
{
    std::ostringstream text;
    text << "HRESULT 0x" << std::hex << std::uppercase << std::setw(8)
         << std::setfill('0') << static_cast<uint32_t>(hr);
    char* message = nullptr;
    if (FormatMessageA(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM
                       | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, static_cast<DWORD>(hr),
                       0, reinterpret_cast<char*>(&message), 0, nullptr)) {
        text << ": " << message;
    }
    if (message) {
        LocalFree(message);
    }
    return text.str();
}

void check(HRESULT hr, const char* operation)
{
    if (FAILED(hr)) {
        throw std::runtime_error(std::string(operation) + " failed: " + hrText(hr));
    }
}

struct ComSession {
    ComSession() { check(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "CoInitializeEx(MTA)"); }
    ~ComSession() { CoUninitialize(); }
    ComSession(const ComSession&) = delete;
    ComSession& operator=(const ComSession&) = delete;
};

struct SystemLibrary {
    HMODULE handle = LoadLibraryExW(L"mfplat.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    SystemLibrary()
    {
        if (!handle) {
            throw std::runtime_error("Media Foundation system DLL mfplat.dll unavailable: "
                + hrText(HRESULT_FROM_WIN32(GetLastError()))
                + "; Windows N/KN or Server may require their optional media components. No encoder fallback is used.");
        }
    }
    ~SystemLibrary() { FreeLibrary(handle); }
    template<typename Function> Function load(const char* name)
    {
        FARPROC address = GetProcAddress(handle, name);
        if (!address) {
            throw std::runtime_error(std::string("Missing mfplat.dll export ") + name
                                     + ": " + hrText(HRESULT_FROM_WIN32(GetLastError())));
        }
        return reinterpret_cast<Function>(address);
    }
};

// No static mfplat.dll import: missing optional OS components are a runtime error.
struct MediaFoundation {
    ComSession com;
    SystemLibrary library;
    decltype(&MFStartup) startup = library.load<decltype(&MFStartup)>("MFStartup");
    decltype(&MFShutdown) shutdown = library.load<decltype(&MFShutdown)>("MFShutdown");
    decltype(&MFCreateMediaType) createType = library.load<decltype(&MFCreateMediaType)>("MFCreateMediaType");
    decltype(&MFCreateSample) createSample = library.load<decltype(&MFCreateSample)>("MFCreateSample");
    decltype(&MFCreateAlignedMemoryBuffer) createBuffer =
        library.load<decltype(&MFCreateAlignedMemoryBuffer)>("MFCreateAlignedMemoryBuffer");
    bool started = false;
    MediaFoundation()
    {
        HRESULT hr = startup(MF_VERSION, MFSTARTUP_FULL);
        if (FAILED(hr)) {
            throw std::runtime_error("MFStartup failed: " + hrText(hr)
                + "; Media Foundation may be unavailable or disabled (including optional N/KN or Server media features).");
        }
        started = true;
    }
    void close()
    {
        if (started) {
            check(shutdown(), "MFShutdown");
            started = false;
        }
    }
    ~MediaFoundation()
    {
        if (started) {
            HRESULT hr = shutdown();
            if (FAILED(hr)) {
                std::cerr << "MFShutdown cleanup error: " << hrText(hr) << '\n';
            }
        }
    }
};

class BufferLock {
public:
    explicit BufferLock(IMFMediaBuffer* buffer) : m_buffer(buffer)
    {
        check(m_buffer->Lock(&data, &capacity, &length), "IMFMediaBuffer::Lock");
    }
    ~BufferLock() { if (m_buffer) { m_buffer->Unlock(); } }
    void unlock() { check(m_buffer->Unlock(), "IMFMediaBuffer::Unlock"); m_buffer = nullptr; }
    BYTE* data = nullptr;
    DWORD capacity = 0;
    DWORD length = 0;
private:
    IMFMediaBuffer* m_buffer;
};

struct EncodeStats {
    uint64_t pcmFrames = 0;
    uint64_t submittedFrames = 0;
    uint64_t paddedFrames = 0;
    uint64_t inputBlocks = 0;
    uint64_t outputSamples = 0;
    uint64_t outputBytes = 0;
    uint64_t notAccepting = 0;
    uint64_t needMoreInput = 0;
    uint64_t outputTimestampsMissing = 0;
    uint64_t outputDurationsMissing = 0;
    std::optional<LONGLONG> firstAvailableOutputTime;
    std::optional<LONGLONG> lastAvailableOutputTime;
    std::optional<LONGLONG> firstAvailableOutputDuration;
};

class SystemAacEncoder {
public:
    SystemAacEncoder(MediaFoundation& mf, UINT32 rate, UINT32 bitrate, std::ostream& destination)
        : m_mf(mf), m_rate(rate), m_destination(destination)
    {
        HRESULT hr = CoCreateInstance(CLSID_AACMFTEncoder, nullptr, CLSCTX_INPROC_SERVER,
                                      IID_PPV_ARGS(m_transform.GetAddressOf()));
        if (FAILED(hr)) {
            throw std::runtime_error("System AAC-LC MFT is unavailable: " + hrText(hr)
                + "; check installed Windows media features (including N/KN and Server). No substitute codec is used.");
        }

        DWORD inputs = 0;
        DWORD outputs = 0;
        check(m_transform->GetStreamCount(&inputs, &outputs), "GetStreamCount");
        if (inputs != 1 || outputs != 1) {
            throw std::runtime_error("Unexpected AAC MFT stream count; exactly one input/output required");
        }
        hr = m_transform->GetStreamIDs(1, &m_inputId, 1, &m_outputId);
        if (hr != E_NOTIMPL) {
            check(hr, "GetStreamIDs");
        }

        ComPtr<IMFMediaType> input;
        check(m_mf.createType(input.GetAddressOf()), "MFCreateMediaType(input)");
        check(input->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio), "input major type");
        check(input->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_PCM), "input PCM subtype");
        check(input->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 16), "input PCM16");
        check(input->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, rate), "input sample rate");
        check(input->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, channels), "input channels");
        check(input->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT, bytesPerFrame), "input alignment");
        check(input->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, rate * bytesPerFrame), "input byte rate");

        ComPtr<IMFMediaType> output;
        check(m_mf.createType(output.GetAddressOf()), "MFCreateMediaType(output)");
        check(output->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio), "output major type");
        check(output->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_AAC), "output AAC subtype");
        check(output->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 16), "output bit depth");
        check(output->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, rate), "output sample rate");
        check(output->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, channels), "output channels");
        check(output->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, bitrate / 8), "output byte rate");
        check(output->SetUINT32(MF_MT_AAC_AUDIO_PROFILE_LEVEL_INDICATION, 0x29), "AAC-LC profile level");
        check(output->SetUINT32(MF_MT_AAC_PAYLOAD_TYPE, 1), "ADTS payload type");

        check(m_transform->SetInputType(m_inputId, input.Get(), MFT_SET_TYPE_TEST_ONLY), "test PCM input type");
        check(m_transform->SetInputType(m_inputId, input.Get(), 0), "set PCM input type");
        check(m_transform->SetOutputType(m_outputId, output.Get(), MFT_SET_TYPE_TEST_ONLY), "test AAC-LC ADTS output type");
        check(m_transform->SetOutputType(m_outputId, output.Get(), 0), "set AAC-LC ADTS output type");
        ComPtr<IMFMediaType> selected;
        check(m_transform->GetOutputCurrentType(m_outputId, selected.GetAddressOf()), "GetOutputCurrentType");
        UINT32 payload = 0;
        UINT32 selectedRate = 0;
        UINT32 selectedChannels = 0;
        UINT32 selectedBytesPerSecond = 0;
        check(selected->GetUINT32(MF_MT_AAC_PAYLOAD_TYPE, &payload), "confirmed payload type");
        check(selected->GetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, &selectedRate), "confirmed sample rate");
        check(selected->GetUINT32(MF_MT_AUDIO_NUM_CHANNELS, &selectedChannels), "confirmed channels");
        check(selected->GetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, &selectedBytesPerSecond), "confirmed bitrate");
        if (payload != 1 || selectedRate != rate || selectedChannels != channels || selectedBytesPerSecond != bitrate / 8) {
            throw std::runtime_error("System MFT did not negotiate the requested ADTS/rate/stereo format");
        }
        check(m_transform->GetInputStreamInfo(m_inputId, &m_inputInfo), "GetInputStreamInfo");
        check(m_transform->ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0), "BEGIN_STREAMING");
        m_streaming = true;
        check(m_transform->ProcessMessage(MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0), "START_OF_STREAM");
    }

    ~SystemAacEncoder()
    {
        if (m_streaming) {
            HRESULT hr = m_transform->ProcessMessage(MFT_MESSAGE_NOTIFY_END_STREAMING, 0);
            if (FAILED(hr)) {
                std::cerr << "END_STREAMING cleanup error: " << hrText(hr) << '\n';
            }
        }
    }

    void pushPcm16(const int16_t* interleaved, size_t frames)
    {
        if (m_finished) {
            throw std::runtime_error("PCM input supplied after drain");
        }
        m_stats.pcmFrames += frames;
        while (frames) {
            const size_t take = std::min(frames, static_cast<size_t>(blockFrames) - m_pending.size() / channels);
            m_pending.insert(m_pending.end(), interleaved, interleaved + take * channels);
            interleaved += take * channels;
            frames -= take;
            if (m_pending.size() == blockFrames * channels) {
                submitBlock();
                m_pending.clear();
            }
        }
    }

    EncodeStats finish()
    {
        if (m_finished || m_stats.pcmFrames == 0) {
            throw std::runtime_error("Empty input or repeated encoder drain");
        }
        if (!m_pending.empty()) {
            m_stats.paddedFrames = blockFrames - m_pending.size() / channels;
            m_pending.resize(blockFrames * channels, 0);
            submitBlock();
            m_pending.clear();
        }
        check(m_transform->ProcessMessage(MFT_MESSAGE_NOTIFY_END_OF_STREAM, m_inputId), "END_OF_STREAM");
        check(m_transform->ProcessMessage(MFT_MESSAGE_COMMAND_DRAIN, 0), "COMMAND_DRAIN");
        pumpOutput();
        check(m_transform->ProcessMessage(MFT_MESSAGE_NOTIFY_END_STREAMING, 0), "END_STREAMING");
        m_streaming = false;
        m_finished = true;
        if (m_stats.outputSamples == 0 || m_stats.outputBytes == 0) {
            throw std::runtime_error("AAC MFT produced no data after drain");
        }
        return m_stats;
    }

private:
    ComPtr<IMFMediaBuffer> allocateBuffer(DWORD size, DWORD alignment)
    {
        if (alignment && (alignment & (alignment - 1))) {
            throw std::runtime_error("MFT requested an unsupported non-power-of-two buffer alignment");
        }
        ComPtr<IMFMediaBuffer> buffer;
        check(m_mf.createBuffer(size, alignment ? alignment - 1 : 0, buffer.GetAddressOf()), "MFCreateAlignedMemoryBuffer");
        return buffer;
    }

    void submitBlock()
    {
        ComPtr<IMFSample> sample;
        check(m_mf.createSample(sample.GetAddressOf()), "MFCreateSample(input)");
        constexpr DWORD inputBytes = blockFrames * bytesPerFrame;
        auto buffer = allocateBuffer(std::max(inputBytes, m_inputInfo.cbSize), m_inputInfo.cbAlignment);
        {
            BufferLock lock(buffer.Get());
            std::memcpy(lock.data, m_pending.data(), inputBytes);
            lock.unlock();
        }
        check(buffer->SetCurrentLength(inputBytes), "input buffer length");
        check(sample->AddBuffer(buffer.Get()), "input AddBuffer");
        const LONGLONG time = static_cast<LONGLONG>(m_stats.submittedFrames * ticksPerSecond / m_rate);
        const LONGLONG end = static_cast<LONGLONG>((m_stats.submittedFrames + blockFrames) * ticksPerSecond / m_rate);
        check(sample->SetSampleTime(time), "input timestamp");
        check(sample->SetSampleDuration(end - time), "input duration");
        for (unsigned attempt = 0; ; ++attempt) {
            HRESULT hr = m_transform->ProcessInput(m_inputId, sample.Get(), 0);
            if (hr == MF_E_NOTACCEPTING) {
                ++m_stats.notAccepting;
                const auto before = m_stats.outputSamples;
                pumpOutput();
                if (attempt >= 8 || m_stats.outputSamples == before) {
                    throw std::runtime_error("AAC MFT rejected input without output progress; refusing infinite retry");
                }
                continue; // Retry the same sample and timestamp.
            }
            check(hr, "ProcessInput");
            break;
        }
        m_stats.submittedFrames += blockFrames;
        ++m_stats.inputBlocks;
        pumpOutput();
    }

    void pumpOutput()
    {
        unsigned emptyResults = 0;
        for (unsigned iteration = 0; iteration < 100000; ++iteration) {
            MFT_OUTPUT_STREAM_INFO info {};
            check(m_transform->GetOutputStreamInfo(m_outputId, &info), "GetOutputStreamInfo");
            ComPtr<IMFSample> supplied;
            if (!(info.dwFlags & (MFT_OUTPUT_STREAM_PROVIDES_SAMPLES | MFT_OUTPUT_STREAM_CAN_PROVIDE_SAMPLES))) {
                if (!info.cbSize) {
                    throw std::runtime_error("AAC MFT requires caller output sample but reports no buffer size");
                }
                check(m_mf.createSample(supplied.GetAddressOf()), "MFCreateSample(output)");
                auto buffer = allocateBuffer(info.cbSize, info.cbAlignment);
                check(supplied->AddBuffer(buffer.Get()), "output AddBuffer");
            }
            MFT_OUTPUT_DATA_BUFFER output {};
            output.dwStreamID = m_outputId;
            output.pSample = supplied.Get();
            DWORD status = 0;
            HRESULT hr = m_transform->ProcessOutput(0, 1, &output, &status);
            ComPtr<IMFCollection> events;
            events.Attach(output.pEvents); // Also released on failure/NEED_MORE_INPUT.
            ComPtr<IMFSample> received;
            if (output.pSample == supplied.Get()) {
                received = supplied;
            } else {
                received.Attach(output.pSample);
            }
            if (hr == MF_E_TRANSFORM_NEED_MORE_INPUT) {
                ++m_stats.needMoreInput;
                return;
            }
            if (hr == MF_E_TRANSFORM_STREAM_CHANGE) {
                throw std::runtime_error("AAC MFT requested an unexpected output format change; no silent renegotiation is performed");
            }
            check(hr, "ProcessOutput");
            // FORMAT_CHANGE, STREAM_END and NO_SAMPLE are alternative values
            // (0x100/0x200/0x300), not independent bits.
            const DWORD bufferStatus = output.dwStatus & 0x300;
            if ((status & MFT_PROCESS_OUTPUT_STATUS_NEW_STREAMS)
                || bufferStatus == MFT_OUTPUT_DATA_BUFFER_FORMAT_CHANGE
                || bufferStatus == MFT_OUTPUT_DATA_BUFFER_STREAM_END) {
                throw std::runtime_error("AAC MFT changed output streams/format unexpectedly");
            }
            if (!received || bufferStatus == MFT_OUTPUT_DATA_BUFFER_NO_SAMPLE) {
                if (++emptyResults > 32) {
                    throw std::runtime_error("AAC MFT returned too many outputs without samples");
                }
                continue;
            }
            DWORD byteLength = 0;
            check(received->GetTotalLength(&byteLength), "output sample length");
            if (!byteLength) {
                if (++emptyResults > 32) {
                    throw std::runtime_error("AAC MFT repeatedly returned empty output");
                }
                continue;
            }
            LONGLONG outputTime = 0;
            hr = received->GetSampleTime(&outputTime);
            if (hr == MF_E_NO_SAMPLE_TIMESTAMP) {
                ++m_stats.outputTimestampsMissing;
            } else {
                check(hr, "output timestamp");
                if (!m_stats.firstAvailableOutputTime) { m_stats.firstAvailableOutputTime = outputTime; }
                m_stats.lastAvailableOutputTime = outputTime;
            }
            LONGLONG outputDuration = 0;
            hr = received->GetSampleDuration(&outputDuration);
            if (hr == MF_E_NO_SAMPLE_DURATION) {
                ++m_stats.outputDurationsMissing;
            } else {
                check(hr, "output duration");
                if (!m_stats.firstAvailableOutputDuration) { m_stats.firstAvailableOutputDuration = outputDuration; }
            }
            ComPtr<IMFMediaBuffer> buffer;
            check(received->ConvertToContiguousBuffer(buffer.GetAddressOf()), "output contiguous buffer");
            BufferLock lock(buffer.Get());
            m_destination.write(reinterpret_cast<const char*>(lock.data), lock.length);
            if (!m_destination) {
                throw std::runtime_error("Failed writing encoded AAC bytes");
            }
            m_stats.outputBytes += lock.length;
            ++m_stats.outputSamples;
            emptyResults = 0;
        }
        throw std::runtime_error("AAC MFT output limit reached; refusing infinite drain");
    }

    MediaFoundation& m_mf;
    UINT32 m_rate;
    std::ostream& m_destination;
    ComPtr<IMFTransform> m_transform;
    MFT_INPUT_STREAM_INFO m_inputInfo {};
    DWORD m_inputId = 0;
    DWORD m_outputId = 0;
    bool m_streaming = false;
    bool m_finished = false;
    std::vector<int16_t> m_pending;
    EncodeStats m_stats;
};

struct AdtsStats { uint64_t frames = 0; uint64_t bytes = 0; };

AdtsStats inspectAdts(const fs::path& path, UINT32 rate, uint64_t pcmFrames)
{
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("Cannot reopen encoded AAC for native ADTS verification");
    }
    const std::vector<unsigned char> data((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    AdtsStats stats;
    while (stats.bytes < data.size()) {
        const size_t at = static_cast<size_t>(stats.bytes);
        if (data.size() - at < 7) {
            throw std::runtime_error("Truncated ADTS header");
        }
        const auto* h = data.data() + at;
        const unsigned expectedIndex = rate == 44100 ? 4 : 3;
        const unsigned channelConfig = ((h[2] & 1) << 2) | (h[3] >> 6);
        const unsigned headerLength = (h[1] & 1) ? 7 : 9;
        const unsigned frameLength = ((h[3] & 3) << 11) | (h[4] << 3) | (h[5] >> 5);
        if (h[0] != 0xff || (h[1] & 0xf6) != 0xf0 || (h[2] >> 6) != 1
            || ((h[2] >> 2) & 0xf) != expectedIndex || channelConfig != channels || (h[6] & 3) != 0) {
            throw std::runtime_error("Output is not the requested AAC-LC stereo ADTS stream");
        }
        if (frameLength <= headerLength || frameLength > data.size() - at) {
            throw std::runtime_error("Invalid or truncated ADTS frame payload");
        }
        ++stats.frames;
        stats.bytes += frameLength;
    }
    const uint64_t expected = (pcmFrames + blockFrames - 1) / blockFrames;
    if (!stats.frames || stats.frames < expected || stats.frames > expected + 4) {
        throw std::runtime_error("ADTS duration/frame count is outside the explicit padding/priming tolerance (0..4 extra frames)");
    }
    return stats;
}

struct Options {
    fs::path output;
    fs::path metadata;
    fs::path pcm;
    UINT32 rate = 48000;
    UINT32 bitrate = 128000;
    double seconds = 1.25;
};

UINT32 parseUint(const std::wstring& text)
{
    size_t end = 0;
    unsigned long number = std::stoul(text, &end);
    if (end != text.size() || number > std::numeric_limits<UINT32>::max()) {
        throw std::runtime_error("Invalid integer option");
    }
    return static_cast<UINT32>(number);
}

Options parseOptions(int argc, wchar_t** argv)
{
    Options options;
    bool secondsSpecified = false;
    for (int i = 1; i < argc; ++i) {
        const std::wstring name = argv[i];
        if (i + 1 == argc) {
            throw std::runtime_error("Every option requires a value");
        }
        const std::wstring value = argv[++i];
        if (name == L"--output") { options.output = value; }
        else if (name == L"--metadata") { options.metadata = value; }
        else if (name == L"--pcm") { options.pcm = value; }
        else if (name == L"--rate") { options.rate = parseUint(value); }
        else if (name == L"--bitrate") { options.bitrate = parseUint(value); }
        else if (name == L"--seconds") {
            size_t end = 0;
            options.seconds = std::stod(value, &end);
            secondsSpecified = true;
            if (end != value.size()) { throw std::runtime_error("Invalid duration"); }
        } else { throw std::runtime_error("Unknown command-line option"); }
    }
    if (options.output.empty() || (options.rate != 44100 && options.rate != 48000)
        || (options.bitrate != 96000 && options.bitrate != 128000 && options.bitrate != 160000 && options.bitrate != 192000)
        || !std::isfinite(options.seconds) || options.seconds < 0.05 || options.seconds > 600.0
        || (!options.pcm.empty() && secondsSpecified)) {
        throw std::runtime_error("Require --output, --rate 44100|48000, --bitrate 96000|128000|160000|192000; duration 0.05..600 seconds or --pcm raw PCM16LE stereo");
    }
    if (options.metadata.empty()) { options.metadata = options.output.wstring() + L".native.json"; }
    if (fs::exists(options.output) || fs::exists(options.metadata) || options.output == options.metadata) {
        throw std::runtime_error("Refusing to overwrite an existing output/metadata file");
    }
    return options;
}

void feedSine(SystemAacEncoder& encoder, UINT32 rate, double seconds)
{
    const uint64_t total = static_cast<uint64_t>(std::llround(seconds * rate));
    constexpr double pi = 3.14159265358979323846;
    for (uint64_t at = 0; at < total; ) {
        // Deliberately non-AAC-sized pushes exercise buffering and final padding.
        const size_t frames = static_cast<size_t>(std::min<uint64_t>(137, total - at));
        std::vector<int16_t> pcm(frames * channels);
        for (size_t i = 0; i < frames; ++i) {
            const double time = static_cast<double>(at + i) / rate;
            pcm[2 * i] = static_cast<int16_t>(std::lround(0.2 * 32767.0 * std::sin(2 * pi * 440.0 * time)));
            pcm[2 * i + 1] = static_cast<int16_t>(std::lround(0.2 * 32767.0 * std::sin(2 * pi * 660.0 * time)));
        }
        encoder.pushPcm16(pcm.data(), frames);
        at += frames;
    }
}

void feedRawPcm(SystemAacEncoder& encoder, const fs::path& path, UINT32 rate)
{
    const auto size = fs::file_size(path);
    if (!size || size % bytesPerFrame || size > static_cast<uint64_t>(rate) * bytesPerFrame * 600) {
        throw std::runtime_error("Raw PCM must contain whole nonempty stereo PCM16LE frames, at most 600 seconds");
    }
    std::ifstream source(path, std::ios::binary);
    if (!source) { throw std::runtime_error("Cannot read raw PCM input"); }
    std::vector<int16_t> pcm(137 * channels);
    while (source) {
        source.read(reinterpret_cast<char*>(pcm.data()), static_cast<std::streamsize>(pcm.size() * sizeof(int16_t)));
        const auto count = source.gcount();
        if (count % bytesPerFrame) { throw std::runtime_error("Incomplete stereo PCM frame"); }
        if (count) { encoder.pushPcm16(pcm.data(), static_cast<size_t>(count) / bytesPerFrame); }
    }
    if (!source.eof()) { throw std::runtime_error("Raw PCM input read failed"); }
}

void writeMetadata(const Options& options, const EncodeStats& stats, const AdtsStats& adts)
{
    std::ofstream file(options.metadata, std::ios::binary);
    if (!file) { throw std::runtime_error("Cannot write native probe metadata"); }
    file << std::setprecision(12)
         << "{\n  \"probe_version\": \"0.1.0\",\n  \"backend\": \"Windows system AAC MFT\",\n"
         << "  \"native_adts_check\": \"PASS\",\n  \"sample_rate\": " << options.rate
         << ",\n  \"channels\": 2,\n  \"bitrate\": " << options.bitrate
         << ",\n  \"pcm_frames\": " << stats.pcmFrames
         << ",\n  \"submitted_frames\": " << stats.submittedFrames
         << ",\n  \"padded_frames\": " << stats.paddedFrames
         << ",\n  \"input_blocks\": " << stats.inputBlocks
         << ",\n  \"output_samples\": " << stats.outputSamples
         << ",\n  \"adts_frames\": " << adts.frames
         << ",\n  \"output_bytes\": " << stats.outputBytes
         << ",\n  \"pcm_duration_seconds\": " << static_cast<double>(stats.pcmFrames) / options.rate
         << ",\n  \"adts_duration_seconds\": " << static_cast<double>(adts.frames * blockFrames) / options.rate
         << ",\n  \"not_accepting_count\": " << stats.notAccepting
         << ",\n  \"need_more_input_count\": " << stats.needMoreInput
         << ",\n  \"output_timestamps_missing\": " << stats.outputTimestampsMissing
         << ",\n  \"output_durations_missing\": " << stats.outputDurationsMissing
         << ",\n  \"first_available_output_time_100ns\": "
         << (stats.firstAvailableOutputTime ? std::to_string(*stats.firstAvailableOutputTime) : "null")
         << ",\n  \"last_available_output_time_100ns\": "
         << (stats.lastAvailableOutputTime ? std::to_string(*stats.lastAvailableOutputTime) : "null")
         << ",\n  \"first_available_output_duration_100ns\": "
         << (stats.firstAvailableOutputDuration ? std::to_string(*stats.firstAvailableOutputDuration) : "null")
         << ",\n  \"decode_validated\": false,\n  \"gapless_validated\": false,\n"
         << "  \"integrated_into_cadence\": false\n}\n";
    file.close();
    if (!file) { throw std::runtime_error("Failed flushing native probe metadata"); }
}
} // namespace

int wmain(int argc, wchar_t** argv)
{
    fs::path partial;
    fs::path createdOutput;
    fs::path createdMetadata;
    bool createdPartial = false;
    try {
        const auto options = parseOptions(argc, argv);
        partial = options.output.wstring() + L".partial";
        if (fs::exists(partial)) { throw std::runtime_error("Refusing to overwrite an existing partial output"); }
        // Negotiate the MFT before creating any output file.
        MediaFoundation mf;
        EncodeStats stats;
        {
            std::ofstream destination;
            SystemAacEncoder encoder(mf, options.rate, options.bitrate, destination);
            destination.open(partial, std::ios::binary);
            if (!destination) { throw std::runtime_error("Cannot create partial AAC destination"); }
            createdPartial = true;
            if (options.pcm.empty()) { feedSine(encoder, options.rate, options.seconds); }
            else { feedRawPcm(encoder, options.pcm, options.rate); }
            stats = encoder.finish();
            destination.close();
            if (!destination) { throw std::runtime_error("Failed flushing partial AAC output"); }
        } // Release all transform/samples before MFShutdown.
        mf.close();
        const auto adts = inspectAdts(partial, options.rate, stats.pcmFrames);
        fs::rename(partial, options.output);
        createdPartial = false;
        createdOutput = options.output;
        createdMetadata = options.metadata;
        writeMetadata(options, stats, adts);
        std::wcout << L"PASS(native ADTS structure only): " << options.output.wstring()
                   << L"; frames=" << adts.frames << L"; rate=" << options.rate
                   << L"; decoded/listened/integrated=NO\n";
        return 0;
    } catch (const std::exception& error) {
        if (createdPartial) { std::error_code ignored; fs::remove(partial, ignored); }
        if (!createdOutput.empty()) { std::error_code ignored; fs::remove(createdOutput, ignored); }
        if (!createdMetadata.empty()) { std::error_code ignored; fs::remove(createdMetadata, ignored); }
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
