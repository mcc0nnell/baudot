cmake_minimum_required(VERSION 3.28)
project(baudot_pjsip_native_t140 LANGUAGES CXX)

if(NOT PJSIP_SOURCE_DIR)
  message(FATAL_ERROR "Set PJSIP_SOURCE_DIR to the pinned clean pjproject checkout")
endif()

# Keep the qualification graph intentionally narrow. PJPROJECT stays an
# external source tree; Baudot builds only the dependency closure required by
# the PJSUA2 native text sender rather than the upstream install/all target.
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
target_compile_features(baudot-pjsip-native-t140 PRIVATE cxx_std_17)
target_link_libraries(baudot-pjsip-native-t140 PRIVATE pjsua2)
