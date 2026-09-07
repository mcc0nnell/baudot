cmake_minimum_required(VERSION 3.19)
project(baudot_celix_capability_runtime LANGUAGES C CXX)

find_package(Celix 2.4.0 REQUIRED)

if(NOT PJSIP_SOURCE_DIR)
  message(FATAL_ERROR "Set PJSIP_SOURCE_DIR to the pinned clean pjsip/pjproject 2.17 checkout")
endif()

# Keep the PJSIP dependency closure narrow and static. Only the signaling-parser
# bundle links PJPROJECT. Admission is a separate Celix service which depends on
# ISignalingParser dynamically and fails closed when that service is absent.
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(PJ_SKIP_EXPERIMENTAL_NOTICE ON CACHE BOOL "" FORCE)
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

set(BAUDOT_CELIX_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/include")

function(baudot_configure_bundle target)
  target_include_directories(${target} PRIVATE "${BAUDOT_CELIX_INCLUDE_DIR}")
  target_compile_features(${target} PRIVATE cxx_std_17)
endfunction()

add_celix_bundle(EvidenceEmitterBundle
  SOURCES src/evidence_emitter_bundle.cc
  SYMBOLIC_NAME "Baudot_EvidenceEmitter"
  NAME "Baudot Evidence Emitter"
  FILENAME "baudot_evidence_emitter"
  VERSION "0.1.0"
  GROUP "baudot/celix-lab"
)
baudot_configure_bundle(EvidenceEmitterBundle)

add_celix_bundle(PjsipSignalingParserBundle
  SOURCES src/pjsip_signaling_parser_bundle.cc
  SYMBOLIC_NAME "Baudot_PjsipSignalingParser"
  NAME "Baudot PJSIP Signaling Parser"
  FILENAME "baudot_pjsip_signaling_parser"
  VERSION "0.1.0"
  GROUP "baudot/celix-lab"
)
baudot_configure_bundle(PjsipSignalingParserBundle)
# pjproject's pjsip target keeps pjlib-util private even though public PJSIP
# parser headers include pjlib-util/scanner.h. Make that compile-time/runtime
# dependency explicit at the parser seam instead of duplicating include paths.
target_link_libraries(PjsipSignalingParserBundle PRIVATE pjsip pjlib-util)

add_celix_bundle(PjsipCallAdmissionBundle
  SOURCES src/pjsip_call_admission_bundle.cc
  SYMBOLIC_NAME "Baudot_PjsipCallAdmission"
  NAME "Baudot PJSIP-backed Call Admission"
  FILENAME "baudot_pjsip_call_admission"
  VERSION "0.3.0"
  GROUP "baudot/celix-lab"
)
baudot_configure_bundle(PjsipCallAdmissionBundle)

add_celix_bundle(FaultInjectedCallAdmissionBundle
  SOURCES src/fault_injected_call_admission_bundle.cc
  SYMBOLIC_NAME "Baudot_FaultInjectedCallAdmission"
  NAME "Baudot Fault Injected Call Admission"
  FILENAME "baudot_fault_injected_call_admission"
  VERSION "0.1.0"
  GROUP "baudot/celix-lab"
)
baudot_configure_bundle(FaultInjectedCallAdmissionBundle)

add_celix_bundle(GoodRealtimeTextBundle
  SOURCES src/good_realtime_text_bundle.cc
  SYMBOLIC_NAME "Baudot_GoodRealtimeText"
  NAME "Baudot Good Realtime Text"
  FILENAME "baudot_good_realtime_text"
  VERSION "0.1.0"
  GROUP "baudot/celix-lab"
)
baudot_configure_bundle(GoodRealtimeTextBundle)

add_celix_bundle(FaultInjectedRealtimeTextBundle
  SOURCES src/fault_injected_realtime_text_bundle.cc
  SYMBOLIC_NAME "Baudot_FaultInjectedRealtimeText"
  NAME "Baudot Fault Injected Realtime Text"
  FILENAME "baudot_fault_injected_realtime_text"
  VERSION "0.1.0"
  GROUP "baudot/celix-lab"
)
baudot_configure_bundle(FaultInjectedRealtimeTextBundle)

function(baudot_add_probe target profile_definition)
  add_celix_bundle(${target}
    SOURCES src/composition_probe_bundle.cc
    SYMBOLIC_NAME "Baudot_${target}"
    NAME "Baudot ${target}"
    FILENAME "baudot_${target}"
    VERSION "0.1.0"
    GROUP "baudot/celix-lab"
  )
  baudot_configure_bundle(${target})
  target_compile_definitions(${target} PRIVATE ${profile_definition})
endfunction()

baudot_add_probe(GoodCompositionProbeBundle BAUDOT_PROFILE_GOOD)
baudot_add_probe(FaultInjectedCompositionProbeBundle BAUDOT_PROFILE_FAULT_INJECTED)
baudot_add_probe(MissingRttCompositionProbeBundle BAUDOT_PROFILE_MISSING_RTT)
baudot_add_probe(ParsedNotAdmittedCompositionProbeBundle BAUDOT_PROFILE_PARSED_NOT_ADMITTED)

# A standalone framework driver is intentionally used for dependency lifecycle
# evidence. It stops only the parser bundle while admission and RTT remain live.
add_executable(baudot_celix_pjsip_lifecycle
  src/pjsip_lifecycle_probe.cc
)
target_include_directories(baudot_celix_pjsip_lifecycle PRIVATE "${BAUDOT_CELIX_INCLUDE_DIR}")
target_compile_features(baudot_celix_pjsip_lifecycle PRIVATE cxx_std_17)
target_link_libraries(baudot_celix_pjsip_lifecycle PRIVATE Celix::framework)
add_dependencies(
  baudot_celix_pjsip_lifecycle
  PjsipSignalingParserBundle
  PjsipCallAdmissionBundle
  GoodRealtimeTextBundle
)

add_celix_container(baudot_celix_good
  BUNDLES
    EvidenceEmitterBundle
    PjsipSignalingParserBundle
    PjsipCallAdmissionBundle
    GoodRealtimeTextBundle
    GoodCompositionProbeBundle
    Celix::shell
    Celix::shell_tui
)

add_celix_container(baudot_celix_fault_injected
  BUNDLES
    EvidenceEmitterBundle
    FaultInjectedCallAdmissionBundle
    FaultInjectedRealtimeTextBundle
    FaultInjectedCompositionProbeBundle
    Celix::shell
    Celix::shell_tui
)

add_celix_container(baudot_celix_missing_rtt
  BUNDLES
    EvidenceEmitterBundle
    PjsipSignalingParserBundle
    PjsipCallAdmissionBundle
    MissingRttCompositionProbeBundle
    Celix::shell
    Celix::shell_tui
)

add_celix_container(baudot_celix_parsed_not_admitted
  BUNDLES
    EvidenceEmitterBundle
    PjsipSignalingParserBundle
    PjsipCallAdmissionBundle
    GoodRealtimeTextBundle
    ParsedNotAdmittedCompositionProbeBundle
    Celix::shell
    Celix::shell_tui
)
