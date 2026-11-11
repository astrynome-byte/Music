// SPDX-License-Identifier: GPL-3.0-only
// Windows-only qualification target for the actual production SDK stream.
// It does not link Qt, AbstractAudioEncoder, the notation engine or a muxer.
#include "windowsaacstream.h"
#include "aacpcm16.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using muse::audio::encode::WindowsAacStream;
using namespace muse::audio::encode::systemaac;

static std::string escaped(const std::string& value)
{
    std::string result;
    for (char ch : value) {
        if (ch == '\\' || ch == '"') { result += '\\'; }
        result += ch;
    }
    return result;
}

static uint64_t adtsFrames(const fs::path& path, uint32_t rate, uint64_t realFrames)
{
    std::ifstream source(path, std::ios::binary);
    const std::vector<unsigned char> data((std::istreambuf_iterator<char>(source)), std::istreambuf_iterator<char>());
    size_t at = 0;
    uint64_t frames = 0;
    while (at < data.size()) {
        if (data.size() - at < 7) { throw std::runtime_error("Truncated ADTS header"); }
        const unsigned char* h = data.data() + at;
        const unsigned header = (h[1] & 1) ? 7 : 9;
        const unsigned size = ((h[3] & 3) << 11) | (h[4] << 3) | (h[5] >> 5);
        const unsigned channels = ((h[2] & 1) << 2) | (h[3] >> 6);
        if (h[0] != 255 || (h[1] & 0xf6) != 0xf0 || (h[2] >> 6) != 1
            || ((h[2] >> 2) & 15) != (rate == 44100 ? 4U : 3U) || channels != 2 || (h[6] & 3)) {
            throw std::runtime_error("Unexpected ADTS profile/rate/channels");
        }
        if (size <= header || size > data.size() - at) { throw std::runtime_error("Truncated ADTS frame"); }
        at += size;
        ++frames;
    }
    const uint64_t minimum = (realFrames + 1023) / 1024;
    if (frames < minimum || frames > minimum + 4) { throw std::runtime_error("Unexpected ADTS duration"); }
    return frames;
}

int wmain(int argc, wchar_t** argv)
{
    try {
        if (argc != 5 || std::wstring(argv[1]) != L"--rate" || std::wstring(argv[3]) != L"--output-root") {
            throw std::runtime_error("Usage: --rate 44100|48000 --output-root path");
        }
        const uint64_t requestedRate = std::stoull(argv[2]);
        if (!isSupportedFormat(requestedRate, 2, 128)) { throw std::runtime_error("Unsupported native test format"); }
        const auto rate = static_cast<uint32_t>(requestedRate);
        const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
        const fs::path folder = fs::path(argv[4]) / (std::to_string(rate) + "-" + std::to_string(nonce));
        if (!fs::create_directories(folder)) { throw std::runtime_error("Native test requires a fresh result directory"); }
        const fs::path audio = folder / "sine.aac";
        std::ofstream destination;
        WindowsAacStream stream(rate, 128, [&destination](const unsigned char* data, size_t size) {
            destination.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(size));
            return bool(destination);
        });
        destination.open(audio, std::ios::binary);
        if (!destination) { throw std::runtime_error("Cannot create native test output"); }
        const uint64_t frames = uint64_t(rate) * 5 / 4;
        uint64_t clipped = 0;
        std::vector<int16_t> pcm;
        constexpr double pi = 3.14159265358979323846;
        for (uint64_t at = 0; at < frames;) {
            const size_t count = static_cast<size_t>(std::min<uint64_t>(137, frames - at));
            std::vector<float> block(count * 2);
            for (size_t i = 0; i < count; ++i) {
                const double time = static_cast<double>(at + i) / rate;
                block[2 * i] = static_cast<float>(.2 * std::sin(2 * pi * 440 * time));
                block[2 * i + 1] = static_cast<float>(.2 * std::sin(2 * pi * 660 * time));
            }
            if (!convertPcm16(block.data(), block.size(), pcm, clipped)) { throw std::runtime_error("PCM conversion rejected sine"); }
            stream.pushPcm16(pcm.data(), count);
            at += count;
        }
        stream.finish();
        destination.close();
        if (!destination) { throw std::runtime_error("Cannot finalize native test file"); }
        const auto stats = stream.stats();
        const uint64_t adts = adtsFrames(audio, rate, frames);
        if (clipped || stats.pcmFrames != frames || stats.outputBytes != fs::file_size(audio)) {
            throw std::runtime_error("Native production stream counters disagree");
        }
        const std::string report = "{\"passed\":true,\"production_stream\":true,\"app_adapter_tested\":false,"
            "\"decoded_signal_checked\":false,\"human_listening\":false,\"rate\":" + std::to_string(rate)
            + ",\"pcm_frames\":" + std::to_string(frames) + ",\"padded_frames\":" + std::to_string(stats.paddedFrames)
            + ",\"adts_frames\":" + std::to_string(adts) + ",\"size_bytes\":" + std::to_string(stats.outputBytes)
            + ",\"output\":\"" + escaped(audio.generic_u8string()) + "\"}";
        std::ofstream metadata(folder / "native.json", std::ios::binary);
        metadata << report << '\n';
        metadata.close();
        if (!metadata) { throw std::runtime_error("Cannot write native test report"); }
        std::cout << "CADENCE_SYSTEM_AAC_NATIVE_BEGIN\n" << report << "\nCADENCE_SYSTEM_AAC_NATIVE_END\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
