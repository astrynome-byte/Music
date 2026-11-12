# SPDX-License-Identifier: GPL-3.0-only
cmake_minimum_required(VERSION 3.22)
project(CadenceNativeFxTests LANGUAGES CXX)
get_filename_component(CADENCE_SOURCE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CADENCE_DSP_DIR "${CADENCE_SOURCE_ROOT}/src/framework/audio/engine/internal/dsp")
set(CADENCE_FX_DIR "${CADENCE_SOURCE_ROOT}/src/framework/audio/engine/internal/fx")
enable_testing()

# These two targets use the production C++17 codec and DSP without Qt or an SDK.
add_executable(native_fx_dsp_tests native_fx_dsp_tests.cpp allocationtracker.cpp "${CADENCE_DSP_DIR}/nativeeffects.cpp")
target_include_directories(native_fx_dsp_tests PRIVATE "${CADENCE_DSP_DIR}")
add_executable(native_fx_config_tests config_codec_tests.cpp)
target_include_directories(native_fx_config_tests PRIVATE "${CADENCE_SOURCE_ROOT}/src/framework")
foreach(target native_fx_dsp_tests native_fx_config_tests)
    target_compile_features(${target} PRIVATE cxx_std_17)
    if(MSVC)
        target_compile_options(${target} PRIVATE /utf-8)
    endif()
    add_test(NAME ${target} COMMAND ${target})
endforeach()

# Factory and QObject model test sources are also provided in this directory.
# They are not standalone pure-DSP targets: their actual upstream muse_global,
# generated configuration, Qt/moc and compile definitions must match the app.
# Qualification receipts record the exact native compiler commands used.
