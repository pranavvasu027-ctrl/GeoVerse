#!/bin/bash
set -e
echo "Compiling C++ Engine for Linux/POSIX..."
g++ -O3 -std=c++17 src/main.cpp src/Graph.cpp -I src -o RouteOptimizer_Web
chmod +x RouteOptimizer_Web
echo "Compilation complete! Binary: ./RouteOptimizer_Web"
