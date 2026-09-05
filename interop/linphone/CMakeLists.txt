cmake_minimum_required(VERSION 3.22)
project(baudot_linphone_native_t140 C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

find_package(LibLinphone REQUIRED)

add_executable(baudot-linphone-native-t140 native_t140_sender.c)
target_link_libraries(baudot-linphone-native-t140 PRIVATE ${LibLinphone_TARGET})

target_compile_options(
  baudot-linphone-native-t140
  PRIVATE
    $<$<C_COMPILER_ID:GNU,Clang>:-Wall;-Wextra;-Werror>
)
