cmake_minimum_required(VERSION 3.10)
project(SmartRouteOptimizer)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(src)
add_executable(RouteOptimizer_Web src/main.cpp src/Graph.cpp)
