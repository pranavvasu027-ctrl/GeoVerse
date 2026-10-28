@echo off
echo ============================================================
echo   Compiling GeoVerse Model 3 C++ Engine (Windows / MinGW)
echo ============================================================
g++ -O3 -std=c++17 src/main.cpp src/Graph.cpp -I src -o RouteOptimizer_Web.exe
if %ERRORLEVEL% EQU 0 (
    echo [OK] Compilation successful: RouteOptimizer_Web.exe
    copy /Y RouteOptimizer_Web.exe RouteOptimizer.exe >nul
) else (
    echo [ERROR] Compilation failed with error code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
