// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence contributors
#include "nativeeffects.h"
#include "allocationtracker.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <new>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace cadence::audio::dsp;
using namespace cadence::tests;
constexpr double PI = 3.141592653589793238462643383279502884;
unsigned checks = 0;
void require(bool condition, const char* message)
{
    if (!condition) {
        throw std::runtime_error(message);
    }
}
void metric(const char* name, double sampleRate, double value)
{
    require(std::isfinite(value), "metric must be finite");
    std::cout << "{\"check\":\"" << name << "\",\"sample_rate\":" << sampleRate
              << ",\"value\":" << value << ",\"passed\":true}\n";
    ++checks;
}

std::vector<float> sine(double rate, double frequency, unsigned channels = 2)
{
    const auto frames = static_cast<std::size_t>(rate * 2.0);
    std::vector<float> result(frames * channels);
    for (std::size_t frame = 0; frame < frames; ++frame) {
        const float value = static_cast<float>(0.025 * std::sin(2.0 * PI * frequency * frame / rate));
        for (unsigned channel = 0; channel < channels; ++channel) {
            result[frame * channels + channel] = value;
        }
    }
    return result;
}

double measuredEqDb(ThreeBandEqualizerSettings settings, double rate, double frequency)
{
    ThreeBandEqualizer effect;
    require(effect.setSettings(settings) && effect.prepare(rate, 2), "EQ preparation failed");
    auto input = sine(rate, frequency);
    auto output = input;
    effect.process(output.data(), output.size() / 2);
    double inEnergy = 0.0, outEnergy = 0.0;
    for (auto index = static_cast<std::size_t>(rate); index < output.size(); index += 2) {
        inEnergy += static_cast<double>(input[index]) * input[index];
        outEnergy += static_cast<double>(output[index]) * output[index];
    }
    return 10.0 * std::log10(outEnergy / inEnergy);
}

std::vector<float> noise(std::size_t frames)
{
    std::mt19937 generator(432005);
    std::uniform_real_distribution<float> value(-0.25f, 0.25f);
    std::vector<float> result(frames * 2);
    for (auto& sample : result) {
        sample = value(generator);
    }
    return result;
}

template<typename Processor>
void processPieces(Processor& processor, std::vector<float>& buffer)
{
    std::size_t offset = 0;
    const std::size_t sizes[] = {1, 13, 64, 257, 4096, 7};
    unsigned block = 0;
    while (offset < buffer.size() / 2) {
        const auto frames = std::min(sizes[block++ % 6], buffer.size() / 2 - offset);
        processor.process(buffer.data() + 2 * offset, frames);
        offset += frames;
    }
}

void eqChecks(double rate)
{
    ThreeBandEqualizerSettings settings;
    for (double gain : {-12.0, 12.0}) {
        settings.midGainDb = gain;
        const auto center = measuredEqDb(settings, rate, 1000.0);
        require(std::abs(center - gain) < 0.015, "parametric center gain mismatch");
        metric(gain > 0 ? "eq_peak_plus12_center_db" : "eq_peak_minus12_center_db", rate, center);
    }
    settings.midGainDb = 12.0;
    settings.midQ = 0.5;
    const double wide = measuredEqDb(settings, rate, 500.0);
    settings.midQ = 4.0;
    const double narrow = measuredEqDb(settings, rate, 500.0);
    require(wide > narrow + 3.0, "higher Q must narrow the peak");
    metric("eq_q_width_difference_db", rate, wide - narrow);
    settings = {};
    settings.lowGainDb = 12.0;
    const double low = measuredEqDb(settings, rate, 20.0);
    const double lowCorner = measuredEqDb(settings, rate, 120.0);
    require(low > 11.8 && std::abs(lowCorner - 6.0) < 0.015, "120Hz low shelf response mismatch");
    require(std::abs(measuredEqDb(settings, rate, 10000.0)) < 0.01, "low shelf must leave high frequencies unchanged");
    metric("eq_low_shelf_20hz_db", rate, low);
    metric("eq_low_shelf_120hz_db", rate, lowCorner);
    settings = {};
    settings.highGainDb = 12.0;
    const double high = measuredEqDb(settings, rate, 18000.0);
    const double highCorner = measuredEqDb(settings, rate, 6000.0);
    require(high > 11.8 && std::abs(highCorner - 6.0) < 0.015, "6kHz high shelf response mismatch");
    require(std::abs(measuredEqDb(settings, rate, 100.0)) < 0.01, "high shelf must leave low frequencies unchanged");
    metric("eq_high_shelf_18khz_db", rate, high);
    metric("eq_high_shelf_6khz_db", rate, highCorner);
    settings = {};
    settings.outputGainDb = -6.0;
    require(std::abs(measuredEqDb(settings, rate, 1000.0) + 6.0) < 0.001, "EQ output trim mismatch");
    metric("eq_output_trim_db", rate, measuredEqDb(settings, rate, 1000.0));

    ThreeBandEqualizer identity;
    identity.prepare(rate, 2);
    auto input = noise(10000);
    auto output = input;
    identity.process(output.data(), output.size() / 2);
    require(output == input, "default EQ must be exact identity");
    metric("eq_default_bit_exact_identity", rate, 1);

    settings = {6.0, -12.0, 750.0, 4.0, 6.0, -2.0};
    ThreeBandEqualizer whole, pieces;
    whole.prepare(rate, 2); pieces.prepare(rate, 2);
    whole.setSettings(settings); pieces.setSettings(settings);
    auto a = input, b = input;
    whole.process(a.data(), a.size() / 2);
    processPieces(pieces, b);
    require(a == b, "EQ must be independent of block partition including ramps");
    metric("eq_block_partition_bit_exact", rate, 1);
    whole.reset();
    std::vector<float> impulse(8192 * 2, 0.0f);
    impulse[0] = 0.1f;
    whole.process(impulse.data(), impulse.size() / 2);
    for (std::size_t frame = 0; frame < impulse.size() / 2; ++frame) {
        require(impulse[2 * frame + 1] == 0.0f, "EQ must not leak left impulse into right");
    }
    metric("eq_stereo_impulse_no_crosstalk", rate, 1);
    ThreeBandEqualizer mono, stereo;
    mono.setSettings(settings); mono.prepare(rate, 1);
    stereo.setSettings(settings); stereo.prepare(rate, 2);
    auto monoSignal = sine(rate, 700.0, 1);
    auto stereoSignal = sine(rate, 700.0, 2);
    mono.process(monoSignal.data(), monoSignal.size());
    stereo.process(stereoSignal.data(), stereoSignal.size() / 2);
    for (std::size_t frame = 0; frame < monoSignal.size(); ++frame) {
        require(monoSignal[frame] == stereoSignal[2 * frame], "mono EQ must match one independent stereo channel");
    }
    metric("eq_mono_matches_stereo_channel", rate, 1);
    whole.setBypassed(true);
    output = input;
    whole.process(output.data(), output.size() / 2);
    require(std::memcmp(output.data(), input.data(), input.size() * sizeof(float)) == 0, "EQ bypass must be bit exact");
    metric("eq_bypass_bit_exact", rate, 1);

    ThreeBandEqualizer changed, fresh;
    settings = {6.0, 12.0, 12000.0, 2.0, 12.0, 0.0};
    changed.setSettings(settings); changed.prepare(8000, 2); changed.prepare(rate, 2);
    fresh.setSettings(settings); fresh.prepare(rate, 2);
    a = input; b = input;
    changed.process(a.data(), a.size() / 2); fresh.process(b.data(), b.size() / 2);
    require(a == b, "sample-rate changes must restore requested shelf/mid frequencies");
    metric("eq_low_rate_to_target_regression", rate, 1);
}

double compressorSteadyDb(double rate, double inputDb, double knee)
{
    LinkedCompressor effect;
    auto settings = effect.settings();
    settings.kneeDb = knee;
    settings.attackMs = 0.1;
    effect.setSettings(settings); effect.prepare(rate, 1);
    const auto amplitude = static_cast<float>(std::pow(10.0, inputDb / 20.0));
    std::vector<float> buffer(static_cast<std::size_t>(rate * 0.1), amplitude);
    effect.process(buffer.data(), buffer.size());
    return 20.0 * std::log10(static_cast<double>(buffer.back()) / amplitude);
}

void compressorChecks(double rate)
{
    require(std::abs(compressorSteadyDb(rate, -30.0, 0.0)) < 1e-6, "below-threshold compressor must be unity");
    const auto steady = compressorSteadyDb(rate, 0.0, 0.0);
    require(std::abs(steady + 13.5) < 0.001, "4:1 above -18dB must reduce 0dB by 13.5dB");
    metric("compressor_steady_reduction_db", rate, -steady);
    require(std::abs(compressorSteadyDb(rate, -21.0, 6.0)) < 0.001, "lower soft-knee join mismatch");
    require(std::abs(compressorSteadyDb(rate, -18.0, 6.0) + 0.5625) < 0.001, "soft-knee midpoint mismatch");
    require(std::abs(compressorSteadyDb(rate, -15.0, 6.0) + 2.25) < 0.001, "upper soft-knee join mismatch");
    metric("compressor_soft_knee_midpoint_db", rate, -compressorSteadyDb(rate, -18.0, 6.0));

    LinkedCompressor timing;
    auto settings = timing.settings(); settings.kneeDb = 0.0;
    timing.setSettings(settings); timing.prepare(rate, 1);
    std::vector<float> attack(static_cast<std::size_t>(rate * 0.01), 1.0f);
    timing.process(attack.data(), attack.size());
    const double attackDb = -20.0 * std::log10(attack.back());
    require(std::abs(attackDb - 13.5 * (1.0 - std::exp(-1.0))) < 0.001, "attack time constant mismatch");
    require(attack.front() > attack.back(), "attack must not apply full reduction instantly");
    metric("compressor_10ms_attack_reduction_db", rate, attackDb);
    std::vector<float> hold(static_cast<std::size_t>(rate * 0.5), 1.0f);
    timing.process(hold.data(), hold.size());
    std::vector<float> release(static_cast<std::size_t>(rate * 0.1), 0.01f);
    timing.process(release.data(), release.size());
    const double releaseDb = -20.0 * std::log10(static_cast<double>(release.back()) / 0.01f);
    require(std::abs(releaseDb - 13.5 * std::exp(-1.0)) < 0.001, "release time constant mismatch");
    require(release.back() > release.front(), "release must actually restore gain");
    metric("compressor_100ms_release_remaining_db", rate, releaseDb);

    LinkedCompressor linked;
    linked.prepare(rate, 2);
    std::vector<float> stereo(10000 * 2);
    for (std::size_t frame = 0; frame < stereo.size() / 2; ++frame) {
        stereo[2 * frame] = 0.8f; stereo[2 * frame + 1] = 0.08f;
    }
    linked.process(stereo.data(), stereo.size() / 2);
    for (std::size_t frame = 0; frame < stereo.size() / 2; ++frame) {
        require(std::abs(stereo[2 * frame] / 0.8 - stereo[2 * frame + 1] / 0.08) < 2e-7,
                "stereo channels must share exactly the same gain");
    }
    metric("compressor_stereo_link_preserves_balance", rate, 1);
    auto input = noise(10000), a = input, b = input;
    LinkedCompressor whole, pieces;
    whole.prepare(rate, 2); pieces.prepare(rate, 2);
    whole.process(a.data(), a.size() / 2); processPieces(pieces, b);
    require(a == b, "compressor must not depend on block partition");
    metric("compressor_block_partition_bit_exact", rate, 1);
    linked.setBypassed(true);
    a = input; linked.process(a.data(), a.size() / 2);
    require(a == input, "compressor bypass must be exact");
    metric("compressor_bypass_bit_exact", rate, 1);
}

void safetyChecks(double rate)
{
    const auto nan = std::numeric_limits<double>::quiet_NaN();
    ThreeBandEqualizer eq;
    LinkedCompressor compressor;
    require(!eq.prepare(nan, 2) && !compressor.prepare(rate, 3), "invalid format must be rejected");
    require(eq.prepare(rate, 2) && compressor.prepare(rate, 2), "valid format must be accepted");
    auto eqSettings = eq.settings(); eqSettings.midFrequencyHz = nan;
    auto compSettings = compressor.settings(); compSettings.ratio = nan;
    require(!eq.setSettings(eqSettings) && !compressor.setSettings(compSettings), "nonfinite settings must be rejected");
    eqSettings = {24.0, 24.0, 12000.0, 8.0, 24.0, 24.0};
    require(eq.setSettings(eqSettings), "extreme finite EQ settings must be accepted");
    auto buffer = noise(10000);
    buffer[0] = std::numeric_limits<float>::infinity();
    buffer[17] = std::numeric_limits<float>::quiet_NaN();
    buffer[19] = -std::numeric_limits<float>::infinity();
    buffer[21] = std::numeric_limits<float>::max();
    allocations = 0; countAllocations = true;
    eq.process(buffer.data(), buffer.size() / 2);
    compressor.process(buffer.data(), buffer.size() / 2);
    countAllocations = false;
    require(allocations == 0, "process must allocate no memory");
    require(std::all_of(buffer.begin(), buffer.end(), [](float v) { return std::isfinite(v); }),
            "active processors must contain NaN/Inf input without poisoning output");
    metric("active_nonfinite_input_containment", rate, 1);
    metric("process_heap_allocations", rate, static_cast<double>(allocations));
    eq.process(nullptr, 0); compressor.process(nullptr, 0);
    for (double frequency : {80.0, 12000.0}) {
        for (double q : {0.2, 8.0}) {
            for (double gain : {-24.0, 24.0}) {
                eqSettings = {gain, gain, frequency, q, gain, 0.0};
                eq.setSettings(eqSettings); eq.reset();
                std::vector<float> impulse(20000, 0.0f); impulse[0] = 0.1f;
                eq.process(impulse.data(), impulse.size() / 2);
                require(std::all_of(impulse.begin(), impulse.end(), [](float v) { return std::isfinite(v); }),
                        "EQ corner parameters must remain finite");
            }
        }
    }
    metric("eq_corner_parameter_impulses_finite", rate, 1);
}
} // namespace

int main()
{
    try {
        std::cout.precision(12);
        for (double rate : {44100.0, 48000.0}) {
            eqChecks(rate);
            compressorChecks(rate);
            safetyChecks(rate);
        }
        std::cout << "{\"status\":\"PASS\",\"checks\":" << checks << "}\n";
        return 0;
    } catch (const std::exception& error) {
        countAllocations = false;
        std::cerr << "DSP check failed: " << error.what() << '\n';
        return 1;
    }
}
