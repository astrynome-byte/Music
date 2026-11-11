# SPDX-License-Identifier: GPL-3.0-only
cmake_minimum_required(VERSION 3.22)
project(cadence_system_aac_qualification LANGUAGES CXX)
if(NOT WIN32 OR NOT MSVC OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "This qualification requires Windows x64 and MSVC/Windows SDK.")
endif()
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CADENCE_NATIVE_GENERATED "" CACHE PATH "Verified harness sources prepared by qualify.py")
if(NOT EXISTS "${CADENCE_NATIVE_GENERATED}/pcm16.cpp" OR NOT EXISTS "${CADENCE_NATIVE_GENERATED}/finalization.cpp")
    message(FATAL_ERROR "Run qualify.py prepare before configuring this recipe.")
endif()
enable_testing()

# Use the committed native test and production stream without editing either.
add_subdirectory(source/test/cadence/system_aac_native production-native)
# The committed stand-alone test originally uses /MT. Qualify the same sources
# with /MD here to match the application runtime; this is a build-policy override.
set_property(TARGET system-aac-native PROPERTY MSVC_RUNTIME_LIBRARY MultiThreadedDLL)

add_executable(system-aac-pcm16 "${CADENCE_NATIVE_GENERATED}/pcm16.cpp")
target_include_directories(system-aac-pcm16 PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/source")

add_executable(system-aac-finalization
    "${CADENCE_NATIVE_GENERATED}/finalization.cpp"
    source/src/framework/global/types/ret.cpp)
target_include_directories(system-aac-finalization PRIVATE
    "${CADENCE_NATIVE_GENERATED}/stubs"
    "${CMAKE_CURRENT_SOURCE_DIR}/source/src/framework"
    "${CMAKE_CURRENT_SOURCE_DIR}/source/src/framework/global")
target_compile_definitions(system-aac-finalization PRIVATE NO_QT_SUPPORT)
foreach(target IN ITEMS system-aac-pcm16 system-aac-finalization)
    target_compile_features(${target} PRIVATE cxx_std_17)
    target_compile_options(${target} PRIVATE /W4 /EHsc /utf-8)
    set_property(TARGET ${target} PROPERTY MSVC_RUNTIME_LIBRARY MultiThreadedDLL)
endforeach()
foreach(case IN ITEMS rails rounding clipping nonfinite null formats)
    add_test(NAME pcm16-${case} COMMAND system-aac-pcm16 ${case})
endforeach()
add_test(NAME finalization-empty-drain COMMAND system-aac-finalization already-drained)
add_test(NAME finalization-late-failure COMMAND system-aac-finalization delayed-failure)

file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/qualification-abi.json" CONTENT
    "{\"pointer_bytes\":${CMAKE_SIZEOF_VOID_P},\"compiler\":\"${CMAKE_CXX_COMPILER_ID}\",\"compiler_version\":\"${CMAKE_CXX_COMPILER_VERSION}\",\"build_type\":\"${CMAKE_BUILD_TYPE}\",\"native_runtime\":\"$<TARGET_PROPERTY:system-aac-native,MSVC_RUNTIME_LIBRARY>\",\"finalization_runtime\":\"$<TARGET_PROPERTY:system-aac-finalization,MSVC_RUNTIME_LIBRARY>\"}\n")
