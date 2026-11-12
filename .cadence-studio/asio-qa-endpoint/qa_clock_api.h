// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <unknwn.h>
#include <cstdint>
#include "third_party/asio/iasiodrv.h"

// Unique QA-only identity. Not the Steinberg sample identity, not a product endpoint.
inline const CLSID CLSID_CadenceQaClock = {0x8176cda0,0x8af9,0x4483,{0xa0,0x3d,0x45,0xee,0x2f,0x9e,0x86,0x4e}};
inline const IID IID_ICadenceQaClockStats = {0x3d5b7d9f,0x1f8b,0x4249,{0x9f,0x1b,0x97,0xb7,0x55,0xef,0xd0,0x1f}};
inline constexpr long QaFramesPerBlock = 256;
inline constexpr long QaOutputChannels = 2;
inline constexpr unsigned QaMaximumRunSeconds = 300;

struct QaClockStats {
    std::uint32_t structureBytes = sizeof(QaClockStats);
    std::uint32_t schemaVersion = 1;
    std::uint64_t callbacks = 0, frames = 0, finiteSamples = 0, nonzeroSamples = 0;
    std::uint64_t nonfiniteSamples = 0, clippedSamples = 0, lateBlocks = 0, callbackErrors = 0;
    double sampleRate = 0, peak = 0, rms = 0;
    std::uint32_t activeChannels = 0, reportWritten = 0;
};

struct ICadenceQaClockStats : IUnknown {
    // Only after stop/automatic ceiling; no mutable output-buffer access is exposed.
    virtual HRESULT STDMETHODCALLTYPE GetStoppedStats(QaClockStats* result, std::uint32_t bytes) = 0;
};
