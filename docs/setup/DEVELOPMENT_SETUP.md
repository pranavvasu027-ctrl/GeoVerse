# GeoVerse AI — Developer Setup Guide

This guide describes how to set up the development environment, install dependencies, and run tests for each module in the **GeoVerse AI** repository.

---

## 1. Prerequisites
- **Python:** 3.10 to 3.14 (64-bit)
- **Git:** Git 2.40+ installed and configured
- **C++ Compiler (Optional for Model 3 rebuilds):** GCC / Clang (Linux/macOS) or MSVC / MinGW (Windows), with C++17 support and CMake 3.15+

---

## 2. Global Test Execution
Run the complete automated test suite across all three models:
```bash
# From repository root
python -m pytest models/ -v
```
Ensure your `PYTHONPATH` includes the model directories:
```powershell
# Windows PowerShell
$env:PYTHONPATH = "$PWD\models\model-1-lulc-urban-growth;$PWD\models\model-2-property-valuation\src;$PWD\models\model-3-smart-root-optimizer"
pytest models/ -v
```

---

## 3. Model-Specific Environments

### Model 1: LULC Classification & Urban Growth
```bash
cd models/model-1-lulc-urban-growth
pip install -r requirements.txt

# Run automated tests (27 unit/regression tests)
pytest tests/test_labeling_app.py -v

# Start in-browser labeling tool
python -m labeling_app.app
# Open http://127.0.0.1:5050
```

### Model 2: Property Valuation & Analytics
```bash
cd models/model-2-property-valuation
pip install -r requirements.txt

# Run automated tests (6 tests)
pytest tests/test_model2.py -v

# Run data processing pipeline
python src/data_processing.py
```

### Model 3: Smart Route Optimizer
```bash
cd models/model-3-smart-root-optimizer
pip install -r requirements.txt

# Run automated tests (3 tests)
pytest tests/test_routing.py -v

# Launch Flask navigation server
python server.py
# Open http://127.0.0.1:5000

# Direct C++ CLI execution test (Windows)
.\RouteOptimizer_Web.exe route "Swargate" "Kalyani Nagar" cost 0
```
