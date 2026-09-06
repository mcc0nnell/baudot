cmake_minimum_required(VERSION 3.19)
project(baudot_celix_capability_runtime LANGUAGES CXX)

find_package(Celix 2.4.0 REQUIRED)

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

add_celix_bundle(GoodCallAdmissionBundle
  SOURCES src/good_call_admission_bundle.cc
  SYMBOLIC_NAME "Baudot_GoodCallAdmission"
  NAME "Baudot Good Call Admission"
  FILENAME "baudot_good_call_admission"
  VERSION "0.1.0"
  GROUP "baudot/celix-lab"
)
baudot_configure_bundle(GoodCallAdmissionBundle)

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

# Bundle order is deliberate. Providers are active before the probe, and the
# shell is started last so CI can issue `stop 0` only after evidence is emitted.
add_celix_container(baudot_celix_good
  BUNDLES
    EvidenceEmitterBundle
    GoodCallAdmissionBundle
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
    GoodCallAdmissionBundle
    MissingRttCompositionProbeBundle
    Celix::shell
    Celix::shell_tui
)
