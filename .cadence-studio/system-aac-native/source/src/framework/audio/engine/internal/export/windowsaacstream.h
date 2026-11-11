// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>

namespace muse::audio::encode {
// SDK-only transport, adapted from the independently tested Windows AAC probe.
// It owns COM/MF on its creating thread; all calls/destruction must use that thread.
class WindowsAacStream
{
public:
    using Output = std::function<bool(const unsigned char*, size_t)>;
    struct Stats {
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
        std::optional<int64_t> firstAvailableOutputTime;
        std::optional<int64_t> lastAvailableOutputTime;
        std::optional<int64_t> firstAvailableOutputDuration;
    };

    WindowsAacStream(uint32_t sampleRate, uint32_t bitRateKbps, Output output);
    ~WindowsAacStream();
    WindowsAacStream(const WindowsAacStream&) = delete;
    WindowsAacStream& operator=(const WindowsAacStream&) = delete;
    void pushPcm16(const int16_t* interleaved, size_t frames);
    void finish();
    Stats stats() const;

private:
    class Impl;
    std::unique_ptr<Impl> m_impl;
};
}
