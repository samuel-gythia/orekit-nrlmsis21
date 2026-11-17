cmake_minimum_required(VERSION 3.20)
project(nrlmsis21_jni C Fortran)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# 1. Locate JNI
find_package(JNI REQUIRED)

# 2. Fortran & C Compiler Flags
if(CMAKE_Fortran_COMPILER_ID MATCHES "GNU")
    # CRITICAL: -cpp -DDBLE forces r8 to selected_real_kind(15, 307) (64-bit double)
    set(CMAKE_Fortran_FLAGS "${CMAKE_Fortran_FLAGS} -cpp -DDBLE -O3 -fPIC")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -O3 -fPIC")
endif()

# 3. Configurable Upstream NRLMSIS 2.1 Source Directory
if(NOT DEFINED NRLMSIS21_SOURCE_DIR OR "${NRLMSIS21_SOURCE_DIR}" STREQUAL "")
    if(DEFINED ENV{NRLMSIS21_SOURCE_DIR} AND NOT "$ENV{NRLMSIS21_SOURCE_DIR}" STREQUAL "")
        set(_NRLMSIS21_DEFAULT_SOURCE_DIR "$ENV{NRLMSIS21_SOURCE_DIR}")
    else()
        set(_NRLMSIS21_DEFAULT_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/NRLMSIS2.1")
    endif()
    set(NRLMSIS21_SOURCE_DIR "${_NRLMSIS21_DEFAULT_SOURCE_DIR}" CACHE PATH
        "Path to directory containing upstream NRLMSIS 2.1 Fortran (.F90) source files")
else()
    set(NRLMSIS21_SOURCE_DIR "${NRLMSIS21_SOURCE_DIR}" CACHE PATH
        "Path to directory containing upstream NRLMSIS 2.1 Fortran (.F90) source files" FORCE)
endif()

get_filename_component(NRLMSIS21_SOURCE_DIR "${NRLMSIS21_SOURCE_DIR}"
    ABSOLUTE BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
message(STATUS "NRLMSIS 2.1 upstream Fortran source directory: ${NRLMSIS21_SOURCE_DIR}")

if(NOT IS_DIRECTORY "${NRLMSIS21_SOURCE_DIR}")
    message(FATAL_ERROR
        "NRLMSIS21_SOURCE_DIR does not exist or is not a directory:\n"
        "  ${NRLMSIS21_SOURCE_DIR}\n"
        "Obtain the NRLMSIS 2.1 Fortran source code from the U.S. Naval Research Laboratory "
        "and pass -DNRLMSIS21_SOURCE_DIR=/path/to/NRLMSIS2.1 to CMake (or set the "
        "NRLMSIS21_SOURCE_DIR environment variable).")
endif()

# 4. Validate All 8 Required Upstream Fortran Files and Module Definitions
set(NRLMSIS21_REQUIRED_FORTRAN_FILES
    msis_constants.F90
    msis_init.F90
    msis_utils.F90
    msis_dfn.F90
    msis_tfn.F90
    msis_gfn.F90
    msis_gtd8d.F90
    msis_calc.F90
)

set(NRLMSIS_UPSTREAM_SOURCES "")
set(NRLMSIS_MISSING_FILES "")
foreach(_f IN LISTS NRLMSIS21_REQUIRED_FORTRAN_FILES)
    set(_full "${NRLMSIS21_SOURCE_DIR}/${_f}")
    if(NOT EXISTS "${_full}" OR IS_DIRECTORY "${_full}")
        list(APPEND NRLMSIS_MISSING_FILES "${_f}")
    else()
        list(APPEND NRLMSIS_UPSTREAM_SOURCES "${_full}")
    endif()
endforeach()

if(NRLMSIS_MISSING_FILES)
    string(JOIN ", " _missing_str ${NRLMSIS_MISSING_FILES})
    message(FATAL_ERROR
        "Missing required upstream NRLMSIS 2.1 Fortran source file(s) in '${NRLMSIS21_SOURCE_DIR}':\n"
        "  Missing: ${_missing_str}\n"
        "  Required (8 files): msis_constants.F90, msis_init.F90, msis_utils.F90, "
        "msis_dfn.F90, msis_tfn.F90, msis_gfn.F90, msis_gtd8d.F90, msis_calc.F90\n"
        "Supply a valid NRLMSIS 2.1 source directory via -DNRLMSIS21_SOURCE_DIR=<path>.")
endif()

# Verify required Fortran modules / entry points exist inside the supplied files
set(_MODULE_CHECKS
    "msis_constants.F90:module[ \t]+msis_constants"
    "msis_init.F90:module[ \t]+msis_init"
    "msis_utils.F90:module[ \t]+msis_utils"
    "msis_dfn.F90:module[ \t]+msis_dfn"
    "msis_tfn.F90:module[ \t]+msis_tfn"
    "msis_gfn.F90:module[ \t]+msis_gfn"
    "msis_calc.F90:module[ \t]+msis_calc"
    "msis_gtd8d.F90:subroutine[ \t]+gtd8d"
)
foreach(_pair IN LISTS _MODULE_CHECKS)
    string(FIND "${_pair}" ":" _sep)
    string(SUBSTRING "${_pair}" 0 ${_sep} _fname)
    math(EXPR _pat_start "${_sep} + 1")
    string(SUBSTRING "${_pair}" ${_pat_start} -1 _pattern)
    file(READ "${NRLMSIS21_SOURCE_DIR}/${_fname}" _fcontent)
    string(TOLOWER "${_fcontent}" _fcontent_lower)
    string(REGEX MATCH "${_pattern}" _matched "${_fcontent_lower}")
    if("${_matched}" STREQUAL "")
        message(FATAL_ERROR
            "Upstream source validation failed for '${NRLMSIS21_SOURCE_DIR}/${_fname}': "
            "expected Fortran declaration matching '${_pattern}' was not found.")
    endif()
endforeach()

set(NRLMSIS_BRIDGE_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/native/nrlmsis21_c_api.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/native/nrlmsis21_jni.c"
)
foreach(_bf IN LISTS NRLMSIS_BRIDGE_SOURCES)
    if(NOT EXISTS "${_bf}")
        message(FATAL_ERROR "Missing project bridge source file: ${_bf}")
    endif()
endforeach()

set(NRLMSIS_SOURCES
    ${NRLMSIS_UPSTREAM_SOURCES}
    ${NRLMSIS_BRIDGE_SOURCES}
)
list(LENGTH NRLMSIS_UPSTREAM_SOURCES _UPSTREAM_COUNT)
message(STATUS "Discovered ${_UPSTREAM_COUNT} upstream NRLMSIS 2.1 Fortran files: ${NRLMSIS_UPSTREAM_SOURCES}")

# 5. Build Shared Library
add_library(nrlmsis21_jni SHARED ${NRLMSIS_SOURCES})

set(_FORTRAN_MOD_DIR "${CMAKE_CURRENT_BINARY_DIR}/fortran_mods")
file(MAKE_DIRECTORY "${_FORTRAN_MOD_DIR}")
set_target_properties(nrlmsis21_jni PROPERTIES
    Fortran_MODULE_DIRECTORY "${_FORTRAN_MOD_DIR}"
)

target_include_directories(nrlmsis21_jni PRIVATE
    ${JNI_INCLUDE_DIRS}
    "${CMAKE_CURRENT_SOURCE_DIR}/native"
    "${NRLMSIS21_SOURCE_DIR}"
    "${_FORTRAN_MOD_DIR}"
)

# 5. Linkage Configuration
if(WIN32)
    target_link_libraries(nrlmsis21_jni PRIVATE ${JNI_LIBRARIES})
    if(MINGW OR CMAKE_Fortran_COMPILER_ID MATCHES "GNU")
        target_link_options(nrlmsis21_jni PRIVATE
            -Wl,--export-all-symbols
            -static
            -static-libgcc
            -static-libgfortran
        )
    endif()
elseif(UNIX AND NOT APPLE)
    target_link_libraries(nrlmsis21_jni PRIVATE ${JNI_LIBRARIES} m)
    set_target_properties(nrlmsis21_jni PROPERTIES
        BUILD_WITH_INSTALL_RPATH TRUE
        INSTALL_RPATH "$ORIGIN"
    )
endif()

set_target_properties(nrlmsis21_jni PROPERTIES
    PREFIX "lib"
    OUTPUT_NAME "nrlmsis21_jni"
)
