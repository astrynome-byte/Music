// SPDX-License-Identifier: GPL-3.0-only
#include "sample_metrics.h"
#include <cmath>
#include <cstdio>
#include <limits>
int main() {
    cadence::qa::SampleMetrics zero;
    if (zero.rms() != 0 || zero.peak != 0) { return 1; }
    for (int i = 0; i < 512; ++i) { zero.add(0); }
    if (zero.finiteSamples != 512 || zero.nonzeroSamples || zero.rms() != 0) { return 2; }
    cadence::qa::SampleMetrics known;
    for (int i = 0; i < 256; ++i) { known.add(i % 2 ? -.25f : .25f); known.add(i % 2 ? -.5f : .5f); }
    if (known.finiteSamples != 512 || known.nonzeroSamples != 512 || known.peak != .5
        || std::abs(known.rms() - std::sqrt(.15625)) > 1e-12 || known.clippedSamples) { return 3; }
    known.add(std::numeric_limits<float>::quiet_NaN()); known.add(std::numeric_limits<float>::infinity());
    known.add(-std::numeric_limits<float>::infinity());
    if (known.nonfiniteSamples != 3 || known.finiteSamples != 512 || !std::isfinite(known.rms())) { return 4; }
    known.add(1); known.add(-2);
    if (known.clippedSamples != 2 || known.peak != 2 || known.finiteSamples != 514) { return 5; }
    std::puts("PASS 5 meaningful output-metric cases; portable arithmetic only, no Windows driver qualification.");
}
