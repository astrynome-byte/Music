// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence contributors
// Standalone DSP candidates; no IFxProcessor adapter or user interface here.
#pragma once

#include <array>
#include <cstddef>

namespace cadence::audio::dsp {

// All process sizes are FRAMES, using interleaved mono/stereo float buffers.
// Prepare/parameter changes/process belong to one serialized engine thread.
// Neither processor allocates or locks while processing.
enum class EqualizerShape { Peak, LowShelf, HighShelf };
struct EqualizerBandSettings {
    double frequencyHz = 1000.0;
    double gainDb = 0.0;
    double q = 1.0;
    EqualizerShape shape = EqualizerShape::Peak;
};

class EqualizerBand {
public:
    bool prepare(double sampleRate, unsigned channels) noexcept;
    bool setSettings(EqualizerBandSettings settings) noexcept;
    EqualizerBandSettings settings() const noexcept { return m_settings; }
    void setBypassed(bool bypassed) noexcept;
    bool bypassed() const noexcept { return m_bypassed; }
    void reset() noexcept;
    void process(float* interleaved, std::size_t frames) noexcept;

private:
    struct Coefficients { double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0; };
    struct State { double z1 = 0.0, z2 = 0.0; };
    Coefficients calculate() const noexcept;
    void updateTarget(bool immediate) noexcept;
    void advanceCoefficients() noexcept;
    EqualizerBandSettings m_settings;
    double m_sampleRate = 0.0;
    unsigned m_channels = 0;
    bool m_bypassed = false;
    Coefficients m_current;
    Coefficients m_target;
    std::size_t m_rampFrames = 0;
    std::array<State, 2> m_state {};
};

struct ThreeBandEqualizerSettings {
    double lowGainDb = 0.0;        // fixed 120 Hz low shelf, slope S=1
    double midGainDb = 0.0;
    double midFrequencyHz = 1000.0;
    double midQ = 1.0;
    double highGainDb = 0.0;       // fixed 6 kHz high shelf, slope S=1
    double outputGainDb = 0.0;
};

class ThreeBandEqualizer {
public:
    bool prepare(double sampleRate, unsigned channels) noexcept;
    bool setSettings(ThreeBandEqualizerSettings settings) noexcept;
    ThreeBandEqualizerSettings settings() const noexcept { return m_settings; }
    void setBypassed(bool bypassed) noexcept;
    bool bypassed() const noexcept { return m_bypassed; }
    void reset() noexcept;
    void process(float* interleaved, std::size_t frames) noexcept;

private:
    ThreeBandEqualizerSettings m_settings;
    std::array<EqualizerBand, 3> m_bands;
    unsigned m_channels = 0;
    double m_gainTarget = 1.0;
    double m_gainCurrent = 1.0;
    double m_gainSmoothing = 0.0;
    bool m_bypassed = false;
};

struct CompressorSettings {
    double thresholdDb = -18.0;
    double ratio = 4.0;
    double kneeDb = 6.0;
    double attackMs = 10.0;
    double releaseMs = 100.0;
    double makeupDb = 0.0;
};

// Feed-forward peak detector. One max(|L|,|R|) detector and gain per frame
// preserve the stereo image. Time values are 1/e gain-reduction constants,
// not promises of brick-wall peak limiting. There is no lookahead or clipping.
class LinkedCompressor {
public:
    bool prepare(double sampleRate, unsigned channels) noexcept;
    bool setSettings(CompressorSettings settings) noexcept;
    CompressorSettings settings() const noexcept { return m_settings; }
    void setBypassed(bool bypassed) noexcept;
    bool bypassed() const noexcept { return m_bypassed; }
    void reset() noexcept;
    double gainReductionDb() const noexcept { return m_reductionDb; }
    void process(float* interleaved, std::size_t frames) noexcept;

private:
    void updateCoefficients() noexcept;
    double targetReduction(double peak) const noexcept;
    CompressorSettings m_settings;
    double m_sampleRate = 0.0;
    unsigned m_channels = 0;
    bool m_bypassed = false;
    double m_attack = 0.0;
    double m_release = 0.0;
    double m_makeupSmoothing = 0.0;
    double m_reductionDb = 0.0;
    double m_makeupDb = 0.0;
};

} // namespace cadence::audio::dsp
