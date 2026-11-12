// SPDX-License-Identifier: GPL-3.0-only
// Test-only replacement of the standard ordinary C++ allocation functions.
// Separate translation unit avoids an optimizer false mismatched-new/delete
// diagnostic when inspecting the deliberate malloc/free implementation.
#include "allocationtracker.h"
#include <cstdlib>
#include <new>
namespace cadence::tests {
bool countAllocations = false;
std::size_t allocations = 0;
}
void* operator new(std::size_t size)
{
    if (cadence::tests::countAllocations) {
        ++cadence::tests::allocations;
    }
    if (auto* value = std::malloc(size ? size : 1)) {
        return value;
    }
    throw std::bad_alloc();
}
void operator delete(void* value) noexcept { std::free(value); }
void operator delete(void* value, std::size_t) noexcept { std::free(value); }
