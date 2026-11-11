// SPDX-License-Identifier: GPL-3.0-only
// Independent SDK-only stream; no Microsoft codec binaries are redistributed.
#include "windowsaacstream.h"
#include "aacpcm16.h"

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <mfapi.h>
#include <mferror.h>
#include <mfidl.h>
#include <mftransform.h>
#include <wmcodecdsp.h>
#include <wrl/client.h>

#include <algorithm>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace muse::audio::encode {
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

} // namespace

using EncodeStats = WindowsAacStream::Stats;

class WindowsAacStream::Impl {
public:
    Impl(UINT32 rate, UINT32 bitrate, WindowsAacStream::Output destination)
        : m_rate(rate), m_destination(std::move(destination))
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

    ~Impl()
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
        requireOwnerThread();
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
        requireOwnerThread();
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
        m_transform.Reset();
        m_mf.close();
        return m_stats;
    }

    EncodeStats stats() const { return m_stats; }

private:
    void requireOwnerThread() const
    {
        if (GetCurrentThreadId() != m_ownerThreadId) {
            throw std::runtime_error("Windows AAC must be used and destroyed on its creating export/MTA thread");
        }
    }

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
            if (!m_destination(lock.data, lock.length)) {
                throw std::runtime_error("Failed writing encoded AAC bytes");
            }
            m_stats.outputBytes += lock.length;
            ++m_stats.outputSamples;
            emptyResults = 0;
        }
        throw std::runtime_error("AAC MFT output limit reached; refusing infinite drain");
    }

    MediaFoundation m_mf;
    UINT32 m_rate;
    WindowsAacStream::Output m_destination;
    ComPtr<IMFTransform> m_transform;
    MFT_INPUT_STREAM_INFO m_inputInfo {};
    DWORD m_inputId = 0;
    DWORD m_outputId = 0;
    const DWORD m_ownerThreadId = GetCurrentThreadId();
    bool m_streaming = false;
    bool m_finished = false;
    std::vector<int16_t> m_pending;
    EncodeStats m_stats;
};


WindowsAacStream::WindowsAacStream(uint32_t sampleRate, uint32_t bitRateKbps, Output output)
{
    if (!systemaac::isSupportedFormat(sampleRate, 2, bitRateKbps) || !output) {
        throw std::invalid_argument("Windows AAC requires stereo 44100/48000 Hz and 96/128/160/192 kbit/s, plus an output callback");
    }
    m_impl = std::make_unique<Impl>(sampleRate, bitRateKbps * 1000, std::move(output));
}

WindowsAacStream::~WindowsAacStream() = default;

void WindowsAacStream::pushPcm16(const int16_t* interleaved, size_t frames)
{
    if (!interleaved && frames) { throw std::invalid_argument("Null PCM16 input"); }
    m_impl->pushPcm16(interleaved, frames);
}

void WindowsAacStream::finish()
{
    m_impl->finish();
}

WindowsAacStream::Stats WindowsAacStream::stats() const
{
    return m_impl->stats();
}
}
