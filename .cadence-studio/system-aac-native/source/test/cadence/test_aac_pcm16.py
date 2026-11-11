# SPDX-License-Identifier: GPL-3.0-only
"""Compile the production PCM16 helper and exercise signal/format boundaries."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "src/framework/audio/engine/internal/export/aacpcm16.h"

#include <iostream>
#include <limits>
#include <string>

using namespace muse::audio::encode::systemaac;

static bool require(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
    }
    return condition;
}

static bool railsAndInterior()
{
    const float input[] = { -1.0f, -0.5f, -0.0f, 0.0f, 0.5f, 1.0f };
    const std::vector<int16_t> expected { -32768, -16384, 0, 0, 16384, 32767 };
    std::vector<int16_t> output { 123 };
    uint64_t clipped = 7;
    return require(convertPcm16(input, 6, output, clipped), "valid block rejected")
           && require(output == expected, "incorrect PCM rails or interior values")
           && require(clipped == 7, "valid rails counted as clipped samples");
}

static bool rounding()
{
    // Half a PCM step rounds away from zero, as required by lround.
    const float input[] = { 1.0f / 65536.0f, -1.0f / 65536.0f,
                            3.0f / 65536.0f, -3.0f / 65536.0f };
    const std::vector<int16_t> expected { 1, -1, 2, -2 };
    std::vector<int16_t> output;
    uint64_t clipped = 0;
    return require(convertPcm16(input, 4, output, clipped), "rounding block rejected")
           && require(output == expected, "half-step rounding is not away from zero")
           && require(clipped == 0, "interior rounding counted as clipping");
}

static bool clipping()
{
    const float input[] = { -1.25f, 1.25f, std::numeric_limits<float>::lowest(),
                            std::numeric_limits<float>::max(), 0.25f };
    const std::vector<int16_t> expected { -32768, 32767, -32768, 32767, 8192 };
    std::vector<int16_t> output;
    uint64_t clipped = 3;
    if (!require(convertPcm16(input, 5, output, clipped), "finite clipped block rejected")
        || !require(output == expected, "finite out-of-range input did not clamp")
        || !require(clipped == 7, "clip counter did not accumulate actual out-of-range samples")) {
        return false;
    }
    return require(convertPcm16(input, 5, output, clipped), "second clipped block rejected")
           && require(clipped == 11, "clip count did not accumulate across blocks");
}

static bool rejectsNonfinite()
{
    const float values[] = { std::numeric_limits<float>::quiet_NaN(),
                             std::numeric_limits<float>::infinity(),
                             -std::numeric_limits<float>::infinity() };
    for (float invalid : values) {
        // An out-of-range value before the invalid sample must not change the
        // accumulated count or leak a partially converted prefix.
        const float input[] = { 1.25f, invalid, 0.0f };
        std::vector<int16_t> output { 100, 200 };
        uint64_t clipped = 9;
        if (!require(!convertPcm16(input, 3, output, clipped), "nonfinite sample accepted")
            || !require(output.empty(), "failed block left output data")
            || !require(clipped == 9, "failed block changed clipping counter")) {
            return false;
        }
    }
    return true;
}

static bool nullAndEmpty()
{
    std::vector<int16_t> output { 100 };
    uint64_t clipped = 4;
    if (!require(!convertPcm16(nullptr, 1, output, clipped), "nonempty null input accepted")
        || !require(output.empty(), "null failure left stale output")
        || !require(clipped == 4, "null failure changed clipping counter")) {
        return false;
    }
    output.push_back(100);
    return require(convertPcm16(nullptr, 0, output, clipped), "empty null input rejected")
           && require(output.empty(), "empty input did not clear output")
           && require(clipped == 4, "empty input changed clipping counter");
}

static bool formats()
{
    static_assert(noexcept(isSupportedFormat(44100, 2, 128)), "format validation must be noexcept");
    const uint32_t rates[] = { 44100, 48000 };
    const uint32_t bitrates[] = { 96, 128, 160, 192 };
    for (uint32_t rate : rates) {
        for (uint32_t bitrate : bitrates) {
            if (!require(isSupportedFormat(rate, 2, bitrate), "supported format rejected")) {
                return false;
            }
        }
    }
    const uint64_t invalidRates[] = { 0, 8000, 22050, 44099, 44101, 47999, 48001, 96000,
                                     (uint64_t(1) << 32) + 44100, (uint64_t(1) << 32) + 48000 };
    for (uint64_t rate : invalidRates) {
        if (!require(!isSupportedFormat(rate, 2, 128), "unsupported sample rate accepted")) {
            return false;
        }
    }
    const uint32_t invalidChannels[] = { 0, 1, 3, 6, 8 };
    for (uint32_t channels : invalidChannels) {
        if (!require(!isSupportedFormat(48000, channels, 128), "unsupported channel count accepted")) {
            return false;
        }
    }
    const uint32_t invalidBitrates[] = { 0, 64, 95, 97, 127, 129, 159, 161, 191, 193, 256, 320 };
    for (uint32_t bitrate : invalidBitrates) {
        if (!require(!isSupportedFormat(48000, 2, bitrate), "unsupported bitrate accepted")) {
            return false;
        }
    }
    return true;
}

int main(int argc, char** argv)
{
    if (argc != 2) {
        return 2;
    }
    const std::string test = argv[1];
    bool passed = false;
    if (test == "rails") { passed = railsAndInterior(); }
    else if (test == "rounding") { passed = rounding(); }
    else if (test == "clipping") { passed = clipping(); }
    else if (test == "nonfinite") { passed = rejectsNonfinite(); }
    else if (test == "null") { passed = nullAndEmpty(); }
    else if (test == "formats") { passed = formats(); }
    return passed ? 0 : 1;
}
'''


class AacPcm16Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CXX", "g++"))
        if not compiler or not shutil.which(compiler[0]):
            raise unittest.SkipTest("A C++17 compiler is required: set CXX or install g++")
        cls._temporary = tempfile.TemporaryDirectory(prefix="cadence-aac-pcm16-")
        cls.addClassCleanup(cls._temporary.cleanup)
        directory = Path(cls._temporary.name)
        source = directory / "test_aac_pcm16.cpp"
        source.write_text(HARNESS, encoding="utf-8")
        cls.executable = directory / ("test_aac_pcm16.exe" if os.name == "nt" else "test_aac_pcm16")
        result = subprocess.run(
            [*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-I", str(REPO), str(source), "-o", str(cls.executable)],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Production PCM16 helper did not compile:\n{result.stdout}\n{result.stderr}")

    def run_case(self, case):
        result = subprocess.run(
            [str(self.executable), case], capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, f"{case}: {result.stdout}{result.stderr}")

    def test_pcm16_rails_and_interior(self):
        self.run_case("rails")

    def test_pcm16_rounds_half_steps_away_from_zero(self):
        self.run_case("rounding")

    def test_pcm16_clamps_finite_extremes_and_accumulates_clips(self):
        self.run_case("clipping")

    def test_nonfinite_block_is_rejected_without_partial_result(self):
        self.run_case("nonfinite")

    def test_null_input_and_empty_block(self):
        self.run_case("null")

    def test_supported_and_unsupported_system_aac_formats(self):
        self.run_case("formats")


if __name__ == "__main__":
    unittest.main()
