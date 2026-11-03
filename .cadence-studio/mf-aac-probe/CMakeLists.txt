# SPDX-License-Identifier: GPL-3.0-only
cmake_minimum_required(VERSION 3.22)
project(cadence_mf_aac_probe VERSION 0.1.0 LANGUAGES CXX)

if(NOT WIN32 OR NOT MSVC OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "This probe requires Windows x64, MSVC and the Windows SDK. It cannot validate Media Foundation on Linux.")
endif()

add_executable(cadence-mf-aac-probe src/mf_aac_probe.cpp)
target_compile_features(cadence-mf-aac-probe PRIVATE cxx_std_17)
target_compile_definitions(cadence-mf-aac-probe PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX
    WINVER=0x0A00 _WIN32_WINNT=0x0A00)
target_compile_options(cadence-mf-aac-probe PRIVATE /W4 /permissive- /EHsc /utf-8)
# GUIDs only from the SDK. MF entry points are loaded from system32 at runtime
# so an absent Media Foundation installation can be reported by main().
target_link_libraries(cadence-mf-aac-probe PRIVATE ole32 mfuuid wmcodecdspuuid)
set_property(TARGET cadence-mf-aac-probe PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

enable_testing()
option(MF_AAC_PROBE_TESTS "Enable the Python-driven Windows encoding tests" ON)
set(MF_AAC_PROBE_RESULTS_DIR "${CMAKE_CURRENT_BINARY_DIR}/probe-results" CACHE PATH "Probe result directories, never overwritten")
if(MF_AAC_PROBE_TESTS)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    foreach(rate IN ITEMS 44100 48000)
        add_test(NAME system-aac-${rate}
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/run_probe_case.py"
                --encoder "$<TARGET_FILE:cadence-mf-aac-probe>" --sample-rate ${rate}
                --results-root "${MF_AAC_PROBE_RESULTS_DIR}")
        set_tests_properties(system-aac-${rate} PROPERTIES TIMEOUT 60)
    endforeach()
endif()
