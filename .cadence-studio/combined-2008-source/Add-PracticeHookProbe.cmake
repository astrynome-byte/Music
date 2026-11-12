# SPDX-License-Identifier: GPL-3.0-only
# Driver-only opt-in target. Reuses application module libraries without editing
# or linking the application target into the probe. Does not install the probe.
if(NOT CMAKE_SOURCE_DIR STREQUAL PROJECT_SOURCE_DIR AND DEFINED PROJECT_SOURCE_DIR)
    return()
endif()
set_property(GLOBAL PROPERTY CADENCE_PRACTICE_RESET_PROBE_SOURCE
    "${CMAKE_CURRENT_LIST_DIR}/MidiPracticeResetProbe.cpp")
function(cadence_add_practice_reset_probe)
    if(NOT WIN32 OR NOT MSVC OR NOT CADENCE_BUILD)
        message(FATAL_ERROR "The optional native hook probe requires the real Windows MSVC Cadence configuration")
    endif()
    if(NOT TARGET MuseScoreStudio OR NOT TARGET notation OR NOT TARGET notationscene)
        message(FATAL_ERROR "Actual application and notation targets must already exist")
    endif()
    get_property(probe_source GLOBAL PROPERTY CADENCE_PRACTICE_RESET_PROBE_SOURCE)
    get_target_property(app_libraries MuseScoreStudio LINK_LIBRARIES)
    if(NOT app_libraries)
        message(FATAL_ERROR "The actual application link libraries are unavailable")
    endif()
    add_executable(cadence_practice_reset_probe EXCLUDE_FROM_ALL "${probe_source}")
    target_compile_features(cadence_practice_reset_probe PRIVATE cxx_std_17)
    target_compile_definitions(cadence_practice_reset_probe PRIVATE CADENCE_BUILD=1 CADENCE_MIDI_ROUTING_TEST=1)
    target_compile_options(cadence_practice_reset_probe PRIVATE /utf-8)
    target_include_directories(cadence_practice_reset_probe PRIVATE
        "${CMAKE_SOURCE_DIR}/src" "${CMAKE_SOURCE_DIR}/src/framework"
        "${CMAKE_SOURCE_DIR}/src/framework/global" "${CMAKE_SOURCE_DIR}/src/notation/internal"
        "${CMAKE_BINARY_DIR}")
    target_link_libraries(cadence_practice_reset_probe PRIVATE ${app_libraries})
    set_target_properties(cadence_practice_reset_probe PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/cadence-practice-probe"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/cadence-practice-probe")
    file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/cadence-practice-probe-path.txt"
        CONTENT "$<TARGET_FILE:cadence_practice_reset_probe>\n")
endfunction()
cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL cadence_add_practice_reset_probe)
