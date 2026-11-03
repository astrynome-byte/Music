# SPDX-License-Identifier: GPL-3.0-only
# Diagnostic fixture only. This executable is never an application deliverable.
cmake_minimum_required(VERSION 3.22)
project(CadencePackagingDiagnostic LANGUAGES CXX)
if(NOT CADENCE_SOURCE_ROOT)
    message(FATAL_ERROR "CADENCE_SOURCE_ROOT must identify the reconstructed application source")
endif()
if(NOT WIN32 AND NOT CADENCE_DIAGNOSTIC_CONFIGURE_ONLY)
    message(FATAL_ERROR "The actual WiX diagnostic requires native Windows")
endif()

list(PREPEND CMAKE_MODULE_PATH "${CADENCE_SOURCE_ROOT}/buildscripts/cmake")
set(CADENCE_BUILD ON CACHE BOOL "Use actual Cadence packaging metadata" FORCE)
set(MUSE_APP_BUILD_MODE release)
include("${CADENCE_SOURCE_ROOT}/version.cmake")
# Match the application release configuration, not version.cmake's initial defaults.
set(MUSE_APP_UNSTABLE OFF)
set(MUSE_APP_IS_PRERELEASE OFF)
if(CADENCE_DIAGNOSTIC_CONFIGURE_ONLY)
    # Linux can inspect generated CPack configuration, but cannot execute WiX.
    set(PLATFORM_DETECTED 1)
    set(OS_IS_WIN 1)
    set(CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS_SKIP TRUE)
endif()

add_executable(CadenceStudio4 diagnostic.cpp)
install(TARGETS CadenceStudio4 RUNTIME DESTINATION bin)
install(FILES DIAGNOSTIC-ONLY.txt DESTINATION .)

# Keep the unchanged packaging module and template. Only the payload is tiny.
# The assets are byte-identical copies made by Run-PackagingDiagnostic.ps1.
set(CPACK_WIX_TEMPLATE "${CADENCE_SOURCE_ROOT}/buildscripts/packaging/Windows/Installer/WIX.template.in")
include("${CADENCE_SOURCE_ROOT}/buildscripts/packaging/Windows/SetupWindowsPackaging.cmake")
