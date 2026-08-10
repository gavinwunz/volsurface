cmake_minimum_required(VERSION 3.18)
project(volsurface_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(pybind11 REQUIRED)

pybind11_add_module(_core black_scholes.cpp)

target_compile_options(_core PRIVATE -O3 -march=native -ffast-math)