cmake_minimum_required(VERSION 3.28)
project(baudot_pjsip_native_t140 LANGUAGES CXX)

if(NOT PJSIP_SOURCE_DIR)
  message(FATAL_ERROR "Set PJSIP_SOURCE_DIR to the pinned clean pjproject checkout")
endif()

# Keep the qualification graph intentionally narrow. PJPROJECT stays an
# external source tree; Baudot builds only the dependency closure required by
# the PJSUA2 native text probes rather than the upstream install/all target.
set(PJ_SKIP_EXPERIMENTAL_NOTICE ON CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_VIDEO OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_SRTP OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_RESAMPLE none CACHE STRING "" FORCE)
set(PJMEDIA_WITH_SPEEX_AEC OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_WEBRTC_AEC OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_WEBRTC_AEC3 OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_GSM_CODEC OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_SPEEX_CODEC OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_ILBC_CODEC OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_G7221_CODEC OFF CACHE BOOL "" FORCE)
set(PJMEDIA_WITH_OPUS_CODEC OFF CACHE BOOL "" FORCE)

add_subdirectory(
  "${PJSIP_SOURCE_DIR}"
  "${CMAKE_BINARY_DIR}/pjproject"
  EXCLUDE_FROM_ALL
)

add_executable(baudot-pjsip-native-t140 native_t140_sender.cpp)
add_executable(baudot-pjsip-native-t140-uas native_t140_uas.cpp)

foreach(target IN ITEMS baudot-pjsip-native-t140 baudot-pjsip-native-t140-uas)
  target_compile_features(${target} PRIVATE cxx_std_17)
  target_link_libraries(${target} PRIVATE pjsua2)
endforeach()

# PJPROJECT's internal targets have the include roots they need to compile, but
# the aggregate PJSUA2 target does not propagate every public/transitive source
# and generated header root to an external source file including <pjsua2.hpp>.
# Make that external-consumer boundary explicit without modifying the pinned
# PJPROJECT checkout.
set(PJPROJECT_BUILD_ROOT "${CMAKE_BINARY_DIR}/pjproject")
set(PJPROJECT_EXTERNAL_INCLUDE_DIRS
  "${PJSIP_SOURCE_DIR}/pjlib/include"
  "${PJSIP_SOURCE_DIR}/pjlib-util/include"
  "${PJSIP_SOURCE_DIR}/pjmedia/include"
  "${PJSIP_SOURCE_DIR}/pjnath/include"
  "${PJSIP_SOURCE_DIR}/pjsip/include"
  "${PJPROJECT_BUILD_ROOT}/pjlib/include"
  "${PJPROJECT_BUILD_ROOT}/pjlib-util/include"
  "${PJPROJECT_BUILD_ROOT}/pjmedia/include"
  "${PJPROJECT_BUILD_ROOT}/pjnath/include"
  "${PJPROJECT_BUILD_ROOT}/pjsip/include"
)

foreach(target IN ITEMS baudot-pjsip-native-t140 baudot-pjsip-native-t140-uas)
  target_include_directories(${target} PRIVATE ${PJPROJECT_EXTERNAL_INCLUDE_DIRS})
endforeach()
