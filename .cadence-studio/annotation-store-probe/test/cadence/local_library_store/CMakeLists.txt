# SPDX-License-Identifier: GPL-3.0-only
cmake_minimum_required(VERSION 3.22)
project(CadenceLocalLibraryStoreTests LANGUAGES CXX)

# A small test target for the actual production store. It needs Qt Core only,
# without loading the score engine, the editor, or an independent application.
find_package(Qt6 6.8 REQUIRED COMPONENTS Core)
get_filename_component(CADENCE_SOURCE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
add_executable(local_library_store_tests
    store_tests.cpp
    "${CADENCE_SOURCE_ROOT}/src/project/internal/localscorelibrarystore.cpp")
target_include_directories(local_library_store_tests PRIVATE "${CADENCE_SOURCE_ROOT}/src/project/internal")
target_compile_features(local_library_store_tests PRIVATE cxx_std_17)
target_link_libraries(local_library_store_tests PRIVATE Qt6::Core)
enable_testing()
add_test(NAME local_library_store COMMAND local_library_store_tests)
