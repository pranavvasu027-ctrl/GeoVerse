# GeoVerse AI: Multimodal Spatio-Temporal Framework for Urban Growth, Property Valuation, and Future Accessibility Analysis

[![Test Suite](https://github.com/pranavvasu027-ctrl/GeoVerse/actions/workflows/python-tests.yml/badge.svg)](https://github.com/pranavvasu027-ctrl/GeoVerse/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![C++: 17](https://img.shields.io/badge/C%2B%2B-17-00599C.svg)](https://isocpp.org/)

**GeoVerse AI** is an integrated spatio-temporal intelligence framework targeting the **Pune Metropolitan Region (PMR)**, India. It couples Earth Observation (EO) satellite remote sensing, hedonic/machine-learning property valuation, and multimodal transport accessibility network optimization into a unified modeling pipeline.

```
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
   Estimates property prices and capital appreciation rates by fusing real geospatial anchors (distances to Metro corridors, highway interchanges, and IT hubs) with infrastructure quality scores.
3. **Model 3: Smart Root Optimizer & Multimodal Accessibility Planning**  
   High-performance C++ graph engine and microservice computing optimal multimodal transit routes (Metro, Bus, Auto, Cab, Pedestrian) across 63 transit hubs in Pune and PCMC, modeling development friction and accessibility contours.

> Detailed architecture diagrams and scientific figures are archived under [`docs/system-architecture/`](docs/system-architecture/) (Figures 1–9 and Master System Architecture).

---

## 2. Repository Structure

```
GeoVerse/
├── README.md                      # Primary project overview and documentation
├── LICENSE                        # MIT License
├── .gitignore                     # Repository exclusions
├── .github/
│   └── workflows/
│       └── python-tests.yml       # Automated CI test workflow
├── docs/
│   ├── system-architecture/       # High-resolution architectural figures (Figs 1–9)
│   ├── research/                  # Research papers, PhD synopsis, and audit evidence
│   └── setup/
│       └── DEVELOPMENT_SETUP.md   # Detailed developer setup instructions
└── models/
    ├── model-1-lulc-urban-growth/ # Model 1: LULC & Satellite Imagery Pipeline
    │   ├── README.md              # Model 1 guide & protocol specifications
    │   ├── requirements.txt       # Dependencies
    │   ├── labeling_app/          # Flask in-browser visual reference labeling application
    │   ├── reports/               # Scientific readiness and dataset audit reports
    │   └── tests/                 # Automated test suite (27 tests)
    ├── model-2-property-valuation/# Model 2: Property Valuation Engine
    │   ├── README.md              # Data provenance, synthetic formula documentation
    │   ├── requirements.txt       # Dependencies
    │   ├── reports/               # Comprehensive progress audit and model status report
    │   ├── src/                   # Feature extraction & dataset generation pipelines
    │   ├── data/                  # Raw locality coordinates and master training tables
    │   └── tests/                 # Automated test suite (6 tests)
    └── model-3-smart-root-optimizer/ # Model 3: Multimodal Pathfinding & Accessibility
        ├── README.md              # C++ routing engine documentation
        ├── requirements.txt       # Microservice dependencies
        ├── src/                   # Custom C++ data structures, Graph, A*, KD-Tree, TSP
        ├── data/                  # Locations and multimodal edges for Pune/PCMC
        ├── server.py              # Flask REST API with live Open-Meteo weather integration
        ├── static/ & templates/   # Leaflet geospatial navigation dashboard
        ├── RouteOptimizer_Web.exe # Pre-compiled high-performance Windows binary
        ├── CMakeLists.txt         # C++ build configuration
        └── tests/                 # Automated test suite (3 tests)
```

---

## 3. Technology Stack

- **Languages:** Python 3.10+, C++17, JavaScript (ES6+), HTML5/CSS3
- **Machine Learning & Analytics:** Scikit-Learn, XGBoost, SHAP, NumPy, Pandas, GeoPandas
- **Geospatial & Remote Sensing:** Landsat Collection 2 Level-2, Sentinel-1 RTC, Copernicus GLO-30 DEM, OpenStreetMap Overpass API
- **Web & Microservices:** Flask 3.0+, Leaflet.js
- **High-Performance Routing:** Custom Bare-Metal C++ Containers (`CustomVector`, `CustomHashMap`, `CustomMinHeap`), 2D Spatial KD-Tree, Held-Karp Bitmask DP

---

## 4. Current Status & Scientific Readiness

To maintain scientific integrity and transparency, the verified status of each model is documented below:

| Component | Code Implementation | Datasets & Infrastructure | Verification Status | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Model 1: LULC Growth** | Complete (Labeling Tool & Protocols) | Samples Ready (1,340 pts); 0 Human Annotations Completed | **Partially Ready (Not Training Ready)** | Confirmatory experiments (C1–C6) are fail-closed (`DO NOT RUN`) until human visual interpretation is completed. Protected evaluator keys are strictly excluded. |
| **Model 2: Property Valuation** | Data Pipeline & Feature Engineering Complete; Model Training & Inference Pending | Real Coordinates + Documented Formulas | **Verified Data Pipeline (Not Training Ready)** | Feature engineering pipeline and real coordinates are operational; model training code (`train.py`, ML models) not yet implemented. Full audit in `reports/MODEL_2_PROGRESS_AUDIT.md`. |
| **Model 3: Smart Root Optimizer** | Complete (C++ Engine + REST Service) | 63 Nodes & Transit Edges Verified | **Verified & Operational** | Solves point-to-point and multi-stop TSP routes in sub-millisecond time. Evaluated for Model 3 accessibility feature extraction. |

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
```

### Running All Automated Tests
```bash
# Run pytest directly from repository root
pytest
# Or with verbose details:
pytest -v
```
**36 test suites covering all three models execute with zero failures.**

---

## 6. Running Individual Models

### Model 1: In-Browser Satellite Reference Labeling Tool
```bash
cd models/model-1-lulc-urban-growth
pip install -r requirements.txt
python -m labeling_app.app
# Open http://127.0.0.1:5050 in your browser
```

### Model 2: Property Valuation Pipeline
```bash
cd models/model-2-property-valuation
pip install -r requirements.txt
python src/data_processing.py
# Outputs master_training_data.csv to data/processed/
```

### Model 3: Multimodal Route Optimizer & UI
```bash
cd models/model-3-smart-root-optimizer
pip install -r requirements.txt
python server.py
# Open http://127.0.0.1:5000 in your browser
```

---

## 7. Data Provenance & Ethics

- **Geospatial Anchors:** Locality centroids, Metro stations, highway junctions, and IT hubs are real, verified coordinates in Pune.
- **Strict Evaluator Holdout:** Model 1's Tier-A Gold evaluation keys (`phase4_gold_key.csv`, `phase6_KEYS_evaluator_only.zip`) are protected research assets and are never committed to public repositories.
- **Synthetic Data Transparency:** Model 2 property transaction records are generated via reproducible deterministic mathematical formulas (`RANDOM_SEED = 42`) seeded by real accessibility distances.
- **KisanCare Independence:** GeoVerse AI is strictly separated from the agricultural assistance project KisanCare.

---

## 8. License

This project is licensed under the [MIT License](LICENSE).
