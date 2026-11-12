# SPDX-License-Identifier: GPL-3.0-only
cmake_minimum_required(VERSION 3.22)
project(CadenceFreeSoundCollectionTests LANGUAGES CXX)
find_package(Qt6 6.8 REQUIRED COMPONENTS Core Network)
get_filename_component(CADENCE_SOURCE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(CMAKE_AUTOMOC ON)
add_executable(free_collection_installer_tests installer_tests.cpp
    "${CADENCE_SOURCE_ROOT}/src/musesounds/internal/freecollectioninstaller.cpp"
    "${CADENCE_SOURCE_ROOT}/src/musesounds/internal/freecollectioninstaller.h")
target_include_directories(free_collection_installer_tests PRIVATE "${CADENCE_SOURCE_ROOT}/src/musesounds/internal")
target_compile_features(free_collection_installer_tests PRIVATE cxx_std_17)
target_link_libraries(free_collection_installer_tests PRIVATE Qt6::Core Qt6::Network)
if(MSVC)
    target_compile_options(free_collection_installer_tests PRIVATE /utf-8)
endif()
# The caller supplies the exact optional upstream bank and its pinned licence.
# No test silently downloads sounds, modifies a user profile or runs the editor.
