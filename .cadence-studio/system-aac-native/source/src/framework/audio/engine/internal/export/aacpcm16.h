/*
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * Copyright (C) 2026 Cadence Studio contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
#ifndef MUSE_AUDIO_ENCODE_AACPCM16_H
#define MUSE_AUDIO_ENCODE_AACPCM16_H

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace muse::audio::encode::systemaac {
inline bool isSupportedFormat(uint64_t rate, uint32_t channels, uint32_t bitrateKbps) noexcept
{
    return (rate == 44100 || rate == 48000) && channels == 2
           && (bitrateKbps == 96 || bitrateKbps == 128 || bitrateKbps == 160 || bitrateKbps == 192);
}

// Samples are interleaved values, not frames. clippedSamples is cumulative across
// successful calls; a rejected block clears output and leaves the counter intact.
// Exactly -1 and +1 are valid input rails, not out-of-range samples.
inline bool convertPcm16(const float* input, size_t interleavedSamples, std::vector<int16_t>& output,
                         uint64_t& clippedSamples)
{
    output.clear();
    if (!input && interleavedSamples != 0) {
        return false;
    }

    // Validate the whole block before changing either output or the clip count.
    for (size_t i = 0; i < interleavedSamples; ++i) {
        if (!std::isfinite(input[i])) {
            return false;
        }
    }

    output.resize(interleavedSamples);
    uint64_t blockClipped = 0;
    for (size_t i = 0; i < interleavedSamples; ++i) {
        const float sample = input[i];
        if (sample < -1.0f || sample > 1.0f) {
            ++blockClipped;
        }

        // Clamp before multiplication/rounding: even the largest finite float
        // must not overflow lround's integer range.
        const double bounded = std::clamp(static_cast<double>(sample), -1.0, 1.0);
        const long rounded = std::lround(bounded * 32768.0);
        output[i] = static_cast<int16_t>(std::clamp(rounded, -32768L, 32767L));
    }

    clippedSamples += blockClipped;
    return true;
}
}

#endif // MUSE_AUDIO_ENCODE_AACPCM16_H
