// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <map>
#include <string>
#include <system_error>

namespace muse::audio::cadencefx {
enum class Kind { None, Equalizer, Compressor };
inline constexpr const char* EQUALIZER_ID = "Cadence EQ";
inline constexpr const char* COMPRESSOR_ID = "Cadence Compressor";
inline constexpr const char* SCHEMA_KEY = "cadence.fx.schema";
using Configuration = std::map<std::string, std::string>;

struct Parameter {
    const char* key;
    const char* label;
    const char* unit;
    double minimum;
    double maximum;
    double step;
    int decimals;
    double initial;
};
inline const std::array<Parameter, 6>& parameters(Kind kind)
{
    static const std::array<Parameter, 6> eq {{
        { "lowGainDb", "Graves · 120 Hz", "dB", -24.0, 24.0, 0.5, 1, 0.0 },
        { "midGainDb", "Médiums", "dB", -24.0, 24.0, 0.5, 1, 0.0 },
        { "midFrequencyHz", "Fréquence des médiums", "Hz", 80.0, 12000.0, 10.0, 0, 1000.0 },
        { "midQ", "Sélectivité des médiums", "Q", 0.2, 8.0, 0.1, 2, 1.0 },
        { "highGainDb", "Aigus · 6 kHz", "dB", -24.0, 24.0, 0.5, 1, 0.0 },
        { "outputGainDb", "Gain de sortie", "dB", -24.0, 24.0, 0.5, 1, 0.0 }
    }};
    static const std::array<Parameter, 6> compressor {{
        { "thresholdDb", "Seuil", "dB", -60.0, 0.0, 0.5, 1, -18.0 },
        { "ratio", "Rapport", ":1", 1.0, 20.0, 0.1, 1, 4.0 },
        { "kneeDb", "Transition douce", "dB", 0.0, 24.0, 0.5, 1, 6.0 },
        { "attackMs", "Attaque", "ms", 0.1, 100.0, 0.5, 1, 10.0 },
        { "releaseMs", "Relâchement", "ms", 10.0, 2000.0, 5.0, 0, 100.0 },
        { "makeupDb", "Gain de compensation", "dB", 0.0, 24.0, 0.5, 1, 0.0 }
    }};
    return kind == Kind::Compressor ? compressor : eq;
}
inline Kind kindForId(const std::string& id)
{
    return id == EQUALIZER_ID ? Kind::Equalizer : id == COMPRESSOR_ID ? Kind::Compressor : Kind::None;
}
struct Settings {
    Kind kind = Kind::None;
    bool supported = false;
    std::array<double, 6> values {};
};
inline Settings defaults(Kind kind)
{
    Settings result;
    result.kind = kind;
    result.supported = kind != Kind::None;
    for (std::size_t i = 0; i < result.values.size(); ++i) { result.values[i] = parameters(kind)[i].initial; }
    return result;
}
inline Settings decode(Kind kind, const Configuration& config)
{
    Settings result = defaults(kind);
    if (!result.supported || config.empty()) { return result; }
    const auto schema = config.find(SCHEMA_KEY);
    if (schema == config.end() || schema->second != "1" || config.size() > 7) {
        result.supported = false;
        return result;
    }
    for (const auto& pair : config) {
        if (pair.first == SCHEMA_KEY) { continue; }
        const auto& specs = parameters(kind);
        auto found = std::find_if(specs.begin(), specs.end(), [&pair](const Parameter& p) { return pair.first == p.key; });
        if (found == specs.end() || pair.second.empty() || pair.second.size() > 64) {
            result.supported = false;
            return result;
        }
        double value = 0.0;
        const auto parsed = std::from_chars(pair.second.data(), pair.second.data() + pair.second.size(), value);
        if (parsed.ec != std::errc() || parsed.ptr != pair.second.data() + pair.second.size() || !std::isfinite(value)
            || value < found->minimum || value > found->maximum) {
            result.supported = false;
            return result;
        }
        result.values[static_cast<std::size_t>(found - specs.begin())] = value;
    }
    return result;
}
inline Configuration encode(const Settings& settings)
{
    Configuration result;
    if (!settings.supported || settings.kind == Kind::None) { return result; }
    result.emplace(SCHEMA_KEY, "1");
    for (std::size_t i = 0; i < settings.values.size(); ++i) {
        const auto& spec = parameters(settings.kind)[i];
        double value = settings.values[i];
        if (!std::isfinite(value)) { value = spec.initial; }
        value = std::clamp(value, spec.minimum, spec.maximum);
        if (value == 0.0) { value = 0.0; }
        char text[64];
        const auto written = std::to_chars(text, text + sizeof(text), value, std::chars_format::general, 17);
        if (written.ec != std::errc()) { return {}; }
        result.emplace(spec.key, std::string(text, written.ptr));
    }
    return result;
}
} // namespace muse::audio::cadencefx
