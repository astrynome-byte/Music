// SPDX-License-Identifier: GPL-3.0-only
// Independent Cadence QA code. Aggregates output only, retains no PCM samples.
#pragma once
#include <cmath>
#include <cstdint>

namespace cadence::qa {
struct SampleMetrics {
    std::uint64_t finiteSamples = 0;
    std::uint64_t nonzeroSamples = 0;
    std::uint64_t nonfiniteSamples = 0;
    std::uint64_t clippedSamples = 0;
    double peak = 0;
    double sumSquares = 0;
    void add(float value) noexcept {
        if (!std::isfinite(value)) { ++nonfiniteSamples; return; }
        const double sample = value;
        const double magnitude = std::fabs(sample);
        ++finiteSamples;
        if (magnitude > 1e-8) { ++nonzeroSamples; }
        if (magnitude >= 1) { ++clippedSamples; }
        if (magnitude > peak) { peak = magnitude; }
        sumSquares += sample * sample;
    }
    double rms() const noexcept { return finiteSamples ? std::sqrt(sumSquares / finiteSamples) : 0; }
};
}
