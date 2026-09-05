cmake_minimum_required(VERSION 3.16)
project(baudot_pjsip_native_t140 LANGUAGES CXX)

find_package(Pj CONFIG REQUIRED)

add_executable(baudot-pjsip-native-t140 native_t140_sender.cpp)
target_compile_features(baudot-pjsip-native-t140 PRIVATE cxx_std_17)
target_link_libraries(baudot-pjsip-native-t140 PRIVATE Pj::pjsua2)
