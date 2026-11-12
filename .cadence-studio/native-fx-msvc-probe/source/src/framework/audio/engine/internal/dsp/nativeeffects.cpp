// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence contributors
// The peaking coefficient arrangement follows the publicly documented RBJ
// Audio EQ Cookbook equations. This is new standalone code, not the unfinished
// MuseScore Equaliser/Compressor implementation. No upstream notice is removed.
#include "nativeeffects.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace cadence::audio::dsp {
namespace {
constexpr double PI = 3.141592653589793238462643383279502884;
bool validFormat(double sampleRate, unsigned channels) noexcept
{
    return std::isfinite(sampleRate) && sampleRate >= 8000.0 && sampleRate <= 384000.0
           && (channels == 1 || channels == 2);
}
float finiteSample(float sample) noexcept { return std::isfinite(sample) ? sample : 0.0f; }
double zapDenormal(double sample) noexcept { return std::abs(sample) < 1e-24 ? 0.0 : sample; }
double linearGain(double db) noexcept { return std::pow(10.0, db / 20.0); }
bool validFrameCount(std::size_t frames, unsigned channels) noexcept
{
    return channels && frames <= std::numeric_limits<std::size_t>::max() / channels;
}
} // namespace

bool EqualizerBand::prepare(double sampleRate, unsigned channels) noexcept
{
    if (!validFormat(sampleRate, channels)) {
        return false;
    }
    m_sampleRate = sampleRate;
    m_channels = channels;
    m_settings.frequencyHz = std::clamp(m_settings.frequencyHz, 5.0, 0.49 * sampleRate);
    updateTarget(true);
    reset();
    return true;
}

bool EqualizerBand::setSettings(EqualizerBandSettings settings) noexcept
{
    if (!std::isfinite(settings.frequencyHz) || !std::isfinite(settings.gainDb) || !std::isfinite(settings.q)) {
        return false;
    }
    if (settings.shape != EqualizerShape::Peak && settings.shape != EqualizerShape::LowShelf
        && settings.shape != EqualizerShape::HighShelf) {
        return false;
    }
    settings.frequencyHz = std::clamp(settings.frequencyHz, 5.0, m_sampleRate ? 0.49 * m_sampleRate : 20000.0);
    settings.gainDb = std::clamp(settings.gainDb, -24.0, 24.0);
    settings.q = std::clamp(settings.q, 0.1, 18.0);
    m_settings = settings;
    if (m_sampleRate) {
        updateTarget(false);
    }
    return true;
}

EqualizerBand::Coefficients EqualizerBand::calculate() const noexcept
{
    if (m_settings.gainDb == 0.0) {
        return {};
    }
    const double a = std::pow(10.0, m_settings.gainDb / 40.0);
    const double omega = 2.0 * PI * m_settings.frequencyHz / m_sampleRate;
    const double cosine = std::cos(omega);
    if (m_settings.shape != EqualizerShape::Peak) {
        const double beta = std::sqrt(2.0 * a) * std::sin(omega); // shelf slope S=1
        if (m_settings.shape == EqualizerShape::LowShelf) {
            const double denominator = (a + 1.0) + (a - 1.0) * cosine + beta;
            return {a * ((a + 1.0) - (a - 1.0) * cosine + beta) / denominator,
                    2.0 * a * ((a - 1.0) - (a + 1.0) * cosine) / denominator,
                    a * ((a + 1.0) - (a - 1.0) * cosine - beta) / denominator,
                    -2.0 * ((a - 1.0) + (a + 1.0) * cosine) / denominator,
                    ((a + 1.0) + (a - 1.0) * cosine - beta) / denominator};
        }
        const double denominator = (a + 1.0) - (a - 1.0) * cosine + beta;
        return {a * ((a + 1.0) + (a - 1.0) * cosine + beta) / denominator,
                -2.0 * a * ((a - 1.0) + (a + 1.0) * cosine) / denominator,
                a * ((a + 1.0) + (a - 1.0) * cosine - beta) / denominator,
                2.0 * ((a - 1.0) - (a + 1.0) * cosine) / denominator,
                ((a + 1.0) - (a - 1.0) * cosine - beta) / denominator};
    }
    const double alpha = std::sin(omega) / (2.0 * m_settings.q);
    const double denominator = 1.0 + alpha / a;
    return {(1.0 + alpha * a) / denominator,
            -2.0 * std::cos(omega) / denominator,
            (1.0 - alpha * a) / denominator,
            -2.0 * std::cos(omega) / denominator,
            (1.0 - alpha / a) / denominator};
}

void EqualizerBand::updateTarget(bool immediate) noexcept
{
    m_target = calculate();
    m_rampFrames = immediate ? 0 : std::max<std::size_t>(1, static_cast<std::size_t>(m_sampleRate * 0.01));
    if (immediate) {
        m_current = m_target;
    }
}

void EqualizerBand::advanceCoefficients() noexcept
{
    if (!m_rampFrames) {
        return;
    }
    const double remaining = static_cast<double>(m_rampFrames);
    m_current.b0 += (m_target.b0 - m_current.b0) / remaining;
    m_current.b1 += (m_target.b1 - m_current.b1) / remaining;
    m_current.b2 += (m_target.b2 - m_current.b2) / remaining;
    m_current.a1 += (m_target.a1 - m_current.a1) / remaining;
    m_current.a2 += (m_target.a2 - m_current.a2) / remaining;
    if (!--m_rampFrames) {
        m_current = m_target;
    }
}

void EqualizerBand::setBypassed(bool bypassed) noexcept
{
    if (m_bypassed != bypassed) {
        m_bypassed = bypassed;
        reset();
    }
}

void EqualizerBand::reset() noexcept
{
    m_state = {};
    m_current = m_target;
    m_rampFrames = 0;
}

void EqualizerBand::process(float* buffer, std::size_t frames) noexcept
{
    if (!buffer || m_bypassed || !validFrameCount(frames, m_channels)) {
        return;
    }
    for (std::size_t frame = 0; frame < frames; ++frame) {
        advanceCoefficients();
        for (unsigned channel = 0; channel < m_channels; ++channel) {
            auto& state = m_state[channel];
            const auto index = frame * m_channels + channel;
            const float input = finiteSample(buffer[index]);
            const double output = m_current.b0 * input + state.z1;
            if (!std::isfinite(output) || std::abs(output) > std::numeric_limits<float>::max()) {
                state = {};
                buffer[index] = 0.0f;
                continue;
            }
            state.z1 = zapDenormal(m_current.b1 * input - m_current.a1 * output + state.z2);
            state.z2 = zapDenormal(m_current.b2 * input - m_current.a2 * output);
            buffer[index] = static_cast<float>(output);
        }
    }
}

bool ThreeBandEqualizer::prepare(double sampleRate, unsigned channels) noexcept
{
    if (!validFormat(sampleRate, channels)) {
        return false;
    }
    m_channels = channels;
    m_gainSmoothing = std::exp(-1.0 / (sampleRate * 0.005));
    for (auto& band : m_bands) {
        band.prepare(sampleRate, channels);
    }
    // Apply the requested fixed shelf and mid frequencies only after each
    // band knows the new rate. Otherwise an old low rate can clamp them.
    setSettings(m_settings);
    reset();
    return true;
}

bool ThreeBandEqualizer::setSettings(ThreeBandEqualizerSettings settings) noexcept
{
    if (!std::isfinite(settings.lowGainDb) || !std::isfinite(settings.midGainDb)
        || !std::isfinite(settings.midFrequencyHz) || !std::isfinite(settings.midQ)
        || !std::isfinite(settings.highGainDb) || !std::isfinite(settings.outputGainDb)) {
        return false;
    }
    settings.lowGainDb = std::clamp(settings.lowGainDb, -24.0, 24.0);
    settings.midGainDb = std::clamp(settings.midGainDb, -24.0, 24.0);
    settings.midFrequencyHz = std::clamp(settings.midFrequencyHz, 80.0, 12000.0);
    settings.midQ = std::clamp(settings.midQ, 0.2, 8.0);
    settings.highGainDb = std::clamp(settings.highGainDb, -24.0, 24.0);
    settings.outputGainDb = std::clamp(settings.outputGainDb, -24.0, 24.0);
    m_settings = settings;
    m_bands[0].setSettings({120.0, settings.lowGainDb, 1.0, EqualizerShape::LowShelf});
    m_bands[1].setSettings({settings.midFrequencyHz, settings.midGainDb, settings.midQ, EqualizerShape::Peak});
    m_bands[2].setSettings({6000.0, settings.highGainDb, 1.0, EqualizerShape::HighShelf});
    m_gainTarget = linearGain(settings.outputGainDb);
    return true;
}

void ThreeBandEqualizer::setBypassed(bool bypassed) noexcept
{
    if (m_bypassed != bypassed) {
        m_bypassed = bypassed;
        reset();
    }
}

void ThreeBandEqualizer::reset() noexcept
{
    for (auto& band : m_bands) {
        band.reset();
    }
    m_gainCurrent = m_gainTarget;
}

void ThreeBandEqualizer::process(float* buffer, std::size_t frames) noexcept
{
    if (!buffer || m_bypassed || !validFrameCount(frames, m_channels)) {
        return;
    }
    for (auto& band : m_bands) {
        band.process(buffer, frames);
    }
    for (std::size_t frame = 0; frame < frames; ++frame) {
        m_gainCurrent = m_gainSmoothing * m_gainCurrent + (1.0 - m_gainSmoothing) * m_gainTarget;
        for (unsigned channel = 0; channel < m_channels; ++channel) {
            const auto index = frame * m_channels + channel;
            const double output = buffer[index] * m_gainCurrent;
            buffer[index] = std::isfinite(output) && std::abs(output) <= std::numeric_limits<float>::max()
                            ? static_cast<float>(output) : 0.0f;
        }
    }
}

bool LinkedCompressor::prepare(double sampleRate, unsigned channels) noexcept
{
    if (!validFormat(sampleRate, channels)) {
        return false;
    }
    m_sampleRate = sampleRate;
    m_channels = channels;
    updateCoefficients();
    reset();
    return true;
}

bool LinkedCompressor::setSettings(CompressorSettings settings) noexcept
{
    if (!std::isfinite(settings.thresholdDb) || !std::isfinite(settings.ratio) || !std::isfinite(settings.kneeDb)
        || !std::isfinite(settings.attackMs) || !std::isfinite(settings.releaseMs) || !std::isfinite(settings.makeupDb)) {
        return false;
    }
    settings.thresholdDb = std::clamp(settings.thresholdDb, -60.0, 0.0);
    settings.ratio = std::clamp(settings.ratio, 1.0, 20.0);
    settings.kneeDb = std::clamp(settings.kneeDb, 0.0, 24.0);
    settings.attackMs = std::clamp(settings.attackMs, 0.1, 100.0);
    settings.releaseMs = std::clamp(settings.releaseMs, 10.0, 2000.0);
    settings.makeupDb = std::clamp(settings.makeupDb, 0.0, 24.0);
    m_settings = settings;
    if (m_sampleRate) {
        updateCoefficients();
    }
    return true;
}

void LinkedCompressor::updateCoefficients() noexcept
{
    m_attack = std::exp(-1.0 / (m_sampleRate * m_settings.attackMs * 0.001));
    m_release = std::exp(-1.0 / (m_sampleRate * m_settings.releaseMs * 0.001));
    m_makeupSmoothing = std::exp(-1.0 / (m_sampleRate * 0.005));
}

void LinkedCompressor::setBypassed(bool bypassed) noexcept
{
    if (m_bypassed != bypassed) {
        m_bypassed = bypassed;
        reset();
    }
}

void LinkedCompressor::reset() noexcept
{
    m_reductionDb = 0.0;
    m_makeupDb = m_settings.makeupDb;
}

double LinkedCompressor::targetReduction(double peak) const noexcept
{
    const double inputDb = peak > 1e-15 ? 20.0 * std::log10(peak) : -300.0;
    const double overshoot = inputDb - m_settings.thresholdDb;
    const double slope = 1.0 - 1.0 / m_settings.ratio;
    const double halfKnee = m_settings.kneeDb / 2.0;
    if (overshoot <= -halfKnee) {
        return 0.0;
    }
    if (m_settings.kneeDb > 0.0 && overshoot < halfKnee) {
        const double distance = overshoot + halfKnee;
        return slope * distance * distance / (2.0 * m_settings.kneeDb);
    }
    return slope * overshoot;
}

void LinkedCompressor::process(float* buffer, std::size_t frames) noexcept
{
    if (!buffer || m_bypassed || !validFrameCount(frames, m_channels)) {
        return;
    }
    for (std::size_t frame = 0; frame < frames; ++frame) {
        double peak = 0.0;
        for (unsigned channel = 0; channel < m_channels; ++channel) {
            const auto index = frame * m_channels + channel;
            buffer[index] = finiteSample(buffer[index]);
            peak = std::max(peak, std::abs(static_cast<double>(buffer[index])));
        }
        const double target = targetReduction(peak);
        const double coefficient = target > m_reductionDb ? m_attack : m_release;
        m_reductionDb = zapDenormal(coefficient * m_reductionDb + (1.0 - coefficient) * target);
        m_makeupDb = m_makeupSmoothing * m_makeupDb + (1.0 - m_makeupSmoothing) * m_settings.makeupDb;
        const double gain = linearGain(m_makeupDb - m_reductionDb);
        for (unsigned channel = 0; channel < m_channels; ++channel) {
            const auto index = frame * m_channels + channel;
            const double output = buffer[index] * gain;
            buffer[index] = std::isfinite(output) && std::abs(output) <= std::numeric_limits<float>::max()
                            ? static_cast<float>(output) : 0.0f;
        }
    }
}
} // namespace cadence::audio::dsp
