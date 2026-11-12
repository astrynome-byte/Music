# SPDX-License-Identifier: GPL-3.0-only
cmake_minimum_required(VERSION 3.22)
project(CadenceAudioIntentNativeProbe LANGUAGES CXX)
set(PROBE_VARIANT "ON" CACHE STRING "ON, OFF or OLD")
set(PROBE_SNAPSHOT_ROOT "" CACHE PATH "Verified source snapshot root")
set(PROBE_OLD_TREE "" CACHE PATH "Verified newly materialized old-engine source tree")
if(PROBE_VARIANT STREQUAL "OLD")
    set(probe_selected_source "${PROBE_OLD_TREE}")
elseif(PROBE_VARIANT STREQUAL "ON" OR PROBE_VARIANT STREQUAL "OFF")
    set(probe_selected_source "${PROBE_SNAPSHOT_ROOT}/candidate")
else()
    message(FATAL_ERROR "Unknown probe variant")
endif()
if(NOT EXISTS "${probe_selected_source}/test/cadence/audio_intent_retention/CMakeLists.txt")
    message(FATAL_ERROR "Verified source snapshot is incomplete")
endif()
execute_process(COMMAND "${CMAKE_COMMAND}"
    "-DPROBE_SOURCE_ROOT=${probe_selected_source}"
    "-DPROBE_CONFIG_OUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}/generated"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/GenerateProbeConfig.cmake"
    COMMAND_ERROR_IS_FATAL ANY)
set(MUSE_GENERATED_CONFIG_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated" CACHE PATH "Actual rendered canonical test configuration" FORCE)
if(PROBE_VARIANT STREQUAL "OFF")
    set(CADENCE_TEST_LEGACY ON CACHE BOOL "Reference behavior" FORCE)
else()
    set(CADENCE_TEST_LEGACY OFF CACHE BOOL "Cadence behavior or old negative control" FORCE)
endif()
add_subdirectory("${probe_selected_source}/test/cadence/audio_intent_retention" production-retention-tests)
