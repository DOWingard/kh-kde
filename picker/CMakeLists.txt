cmake_minimum_required(VERSION 3.20)
project(kingdomhearts-keyblades LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# The plugin lands in plugins/plasma/containmentactions/, a folder that can be
# put on QT_PLUGIN_PATH as it is.
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/plugins)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
# Installation is done by the project's install script, not by CMake.
# kcoreaddons_add_plugin makes a static plugin unless shared libraries are on.
set(BUILD_SHARED_LIBS ON)
set(KCOREADDONS_INTERNAL_SKIP_PLUGIN_INSTALLATION ON)

find_package(Qt6 6.6 REQUIRED COMPONENTS Core Gui Widgets)
find_package(KF6CoreAddons REQUIRED)
find_package(KF6Config REQUIRED)
find_package(Plasma REQUIRED)

add_library(khkeyblades STATIC keyblades.cpp keyblades.h khlog.cpp khlog.h)
set_target_properties(khkeyblades PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(khkeyblades PUBLIC Qt6::Gui KF6::ConfigCore)
target_compile_options(khkeyblades PRIVATE -Wall -Wextra)

kcoreaddons_add_plugin(kingdomhearts_keyblades SOURCES browser.cpp INSTALL_NAMESPACE "plasma/containmentactions")
# Plasma loads the plugin by file name, which is also its id: no "lib" prefix.
set_target_properties(kingdomhearts_keyblades PROPERTIES OUTPUT_NAME kingdomhearts_keyblades PREFIX "")
target_link_libraries(kingdomhearts_keyblades PRIVATE khkeyblades Qt6::Widgets KF6::CoreAddons Plasma::Plasma)
target_compile_options(kingdomhearts_keyblades PRIVATE -Wall -Wextra)

add_executable(kh-keyblade kh-keyblade.cpp)
target_link_libraries(kh-keyblade PRIVATE khkeyblades)
target_compile_options(kh-keyblade PRIVATE -Wall -Wextra)

add_executable(kh-keyblade-preview preview.cpp)
target_link_libraries(kh-keyblade-preview PRIVATE khkeyblades Qt6::Widgets Plasma::Plasma)
target_compile_options(kh-keyblade-preview PRIVATE -Wall -Wextra)
