# GeoVerse AI: Multimodal Spatio-Temporal Framework for Urban Growth, Property Valuation, and Future Accessibility Analysis

[![Test Suite](https://github.com/pranavvasu027-ctrl/GeoVerse/actions/workflows/python-tests.yml/badge.svg)](https://github.com/pranavvasu027-ctrl/GeoVerse/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![C++: 17](https://img.shields.io/badge/C%2B%2B-17-00599C.svg)](https://isocpp.org/)

**GeoVerse AI** is an integrated spatio-temporal intelligence framework targeting the **Pune Metropolitan Region (PMR)**, India. It couples Earth Observation (EO) satellite remote sensing, hedonic/machine-learning property valuation, and multimodal transport accessibility network optimization into a unified modeling pipeline.

```text
Remote Sensing & Spatial Indicators
              │
              ▼
    Model 1 (Urban Growth)
          ┌────┴────┐
          ▼         ▼
Model 2 (Property)  Model 3 (Accessibility)
```

---

## 1. System Architecture & Master Design

The system couples three distinct analytical models across the Pune Metropolitan Region ($15,640\text{ km}^2$, UTM Zone 43N / `EPSG:32643`):

1. **Model 1: Land Use / Land Cover (LULC) Classification & Spatio-Temporal Urban Growth Simulation**  
   Processes multi-decadal satellite imagery (Landsat 5/7/8/9, Sentinel-1 SAR, Copernicus GLO-30 DEM) to monitor land conversion dynamics across four epochs (1990, 2000, 2010, 2020) and forecast future expansion probabilities ($\tilde{U} \in [0, 1]$).
2. **Model 2: Hedonic Property Valuation & Urban Analytics**  
   Estimates property prices, prediction intervals, and what-if infrastructure scenario impacts by fusing real geospatial anchors (distances to Metro corridors, highway interchanges, and IT hubs) with infrastructure quality scores and multimodal transit travel times.
3. **Model 3: Smart Root Optimizer & Multimodal Accessibility Planning**  
   High-performance C++ graph engine and microservice computing optimal multimodal transit routes (Metro, Bus, Auto, Cab, Pedestrian) across 63 transit hubs in Pune and PCMC, modeling development friction and accessibility contours.

> Detailed architecture diagrams and scientific figures are archived under [`docs/system-architecture/`](docs/system-architecture/) (Figures 1–9 and Master System Architecture).

---

## 2. Repository Structure

```text
GeoVerse/
├── README.md                      # Primary project overview and documentation
├── LICENSE                        # MIT License
├── .gitignore                     # Repository exclusions
├── .github/
│   └── workflows/
│       └── python-tests.yml       # Automated CI test workflow (matrix Python 3.10-3.12)
├── docs/
│   ├── system-architecture/       # High-resolution architectural figures (Figs 1–9)
│   ├── research/                  # Research papers, PhD synopsis, and audit evidence
│   └── setup/
│       └── DEVELOPMENT_SETUP.md   # Detailed developer setup instructions
├── models/
│   ├── model-1-lulc-urban-growth/ # Model 1: LULC & Satellite Imagery Pipeline
│   │   ├── README.md              # Model 1 guide & protocol specifications
│   │   ├── requirements.txt       # Dependencies
│   │   ├── labeling_app/          # Flask visual reference labeling application
│   │   ├── db/migrations/         # Supabase PostgreSQL DDL and RLS security policies
│   │   ├── reports/               # Scientific readiness and dataset audit reports
│   │   └── tests/                 # Automated test suite (69 tests)
│   ├── model-2-property-valuation/# Model 2: Property Valuation Engine
│   │   ├── README.md              # Data provenance, synthetic formula documentation
│   │   ├── requirements.txt       # Dependencies
│   │   ├── reports/               # Comprehensive progress audit and model status report
│   │   ├── src/                   # Feature extraction, ML pipeline, scenario engine, REST API
│   │   ├── data/                  # Raw locality coordinates and master training tables
│   │   └── tests/                 # Automated test suite (12 tests)
│   └── model-3-smart-root-optimizer/ # Model 3: Multimodal Pathfinding & Accessibility
│       ├── README.md              # C++ routing engine documentation
│       ├── requirements.txt       # Microservice dependencies
│       ├── src/                   # Custom C++ data structures, Graph, A*, KD-Tree, TSP, accessibility bridge
│       ├── data/                  # Locations and multimodal edges for Pune/PCMC
│       ├── server.py              # Flask REST API with live Open-Meteo weather integration
│       ├── static/ & templates/   # Leaflet geospatial navigation dashboard
│       ├── RouteOptimizer_Web.exe # Pre-compiled high-performance Windows binary
│       ├── Makefile, build.bat, build.sh # Native C++ build configurations
│       ├── Dockerfile             # Containerized Linux deployment specification
│       └── tests/                 # Automated test suite (14 tests)
└── tests/
    └── test_e2e_integration.py    # Cross-model end-to-end integration test suite (6 tests)
```

---

## 3. Technology Stack

- **Languages:** Python 3.10+, C++17, JavaScript (ES6+), HTML5/CSS3
- **Machine Learning & Analytics:** Scikit-Learn, Random Forest, ColumnTransformer, NumPy, Pandas, GeoPandas
- **Geospatial & Remote Sensing:** Landsat Collection 2 Level-2 (Planetary Computer STAC), Copernicus GLO-30 DEM, OpenStreetMap Overpass API
- **Web & Microservices:** Flask 3.0+, Leaflet.js
- **High-Performance Routing:** Custom Bare-Metal C++ Containers (`CustomVector`, `CustomHashMap`, `CustomMinHeap`), 2D Spatial KD-Tree, Held-Karp Bitmask DP

---

## 4. Current Status & Scientific Readiness

To maintain scientific integrity and transparency, the verified status of each model is documented below:

| Component | Code Implementation | Datasets & Infrastructure | Verification Status | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Model 1: LULC Growth** | Complete (Labeling Tool, Dual Backend Storage, Migration Tooling) | Samples Ready (1,340 pts); 1 Complete, 2 Incomplete T1; Feature Cube Absent | **Partially Ready (Training Blocked)** | Scientific gate remains fail-closed (`BLOCKED` / `DO NOT RUN`) until `pune_G30.zarr` is provisioned and visual interpretation is complete. Storage active on JSON. |
| **Model 2: Property Valuation** | Complete (Feature Engineering, ML Pipeline, What-If Simulator, REST API) | Real Coordinates + Documented Formulas | **Verified Pipeline (Trained on Documented Synthetic Data)** | Random Forest pipeline with temporal holdout split (train $\le 2023$, test $2024$); interfaces with Model 3 transit travel times. Provenance explicitly labeled. |
| **Model 3: Smart Root Optimizer** | Complete (C++ Engine + REST Service + Leaflet HUD) | 63 Nodes & Transit Edges Verified | **Verified & Operational** | Solves point-to-point and multi-stop TSP routes; simulated traffic clearly labeled; reproducible C++ build tooling for Windows/Linux. |
| **Cross-Model Integration** | Complete (Model 2 $\leftrightarrow$ Model 3 accessibility bridge; E2E Test Suite) | Unified Test Fixtures & Health Contracts | **Verified Cross-Model Integration** | Model 2 queries Model 3 transit indicators with graceful offline fallback; unified scenario analysis verified. |

---

## 5. Quickstart & Installation

### Global Requirements Installation
```bash
# Clone the repository
git clone https://github.com/pranavvasu027-ctrl/GeoVerse.git
cd GeoVerse

# Recommended: create a virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r models/model-1-lulc-urban-growth/requirements.txt
pip install -r models/model-2-property-valuation/requirements.txt
pip install -r models/model-3-smart-root-optimizer/requirements.txt
```

### Running All Automated Tests
```bash
# Run pytest directly from repository root
pytest -v
```
**101 automated tests covering all three models and cross-model E2E integration execute with zero failures.**

---

## 6. Running Individual Models

### Model 1: In-Browser Satellite Reference Labeling Tool
```bash
cd models/model-1-lulc-urban-growth
python -m labeling_app.app
# Open http://127.0.0.1:5050 in your browser
```

### Model 2: Property Valuation REST API
```bash
cd models/model-2-property-valuation
python src/api.py
# Microservice running on http://127.0.0.1:5001
```

### Model 3: Multimodal Route Optimizer & UI
```bash
cd models/model-3-smart-root-optimizer
python server.py
# Open http://127.0.0.1:5000 in your browser
```

---

## 7. Data Provenance & Ethics

- **Geospatial Anchors:** Locality centroids, Metro stations, highway junctions, and IT hubs are real, verified coordinates in Pune.
- **Strict Evaluator Holdout:** Model 1's Tier-A Gold evaluation holdout (641 samples) is strictly preserved and excluded from training.
- **Synthetic Data Transparency:** Model 2 property transaction records are generated via reproducible deterministic mathematical formulas (`RANDOM_SEED = 42`) seeded by real accessibility distances, clearly labeled as synthetic across all APIs and checkpoints.
- **Simulated Traffic Disclaimer:** Model 3 rush-hour delays are calculated via heuristic multiplier algorithms, not presented as real-time measured sensor telemetry.
- **KisanCare Independence:** GeoVerse AI is strictly separated from the agricultural assistance project KisanCare.

---

## 8. License

This project is licensed under the [MIT License](LICENSE).
