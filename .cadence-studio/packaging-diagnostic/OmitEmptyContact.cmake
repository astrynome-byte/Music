# SPDX-License-Identifier: GPL-3.0-only
# One-variable experiment, applied at CPack time after the real CPackConfig.cmake.
# An empty defined contact may become an invalid empty WiX Property/@Value.
if(DEFINED CPACK_PACKAGE_CONTACT AND "${CPACK_PACKAGE_CONTACT}" STREQUAL "")
    unset(CPACK_PACKAGE_CONTACT)
endif()
