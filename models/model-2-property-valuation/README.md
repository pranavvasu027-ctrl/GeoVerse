# Model 2: Property Valuation & Urban Spatial Analytics

## 1. Overview
Model 2 predicts real-estate valuation and evaluates scenario impacts across key micro-markets in the Pune Metropolitan Region. It combines:
1. **Real geospatial indicator layers** (distances to Metro stations, major highways, IT parks, and OpenStreetMap Points of Interest).
2. **Infrastructure scoring** derived from empirical accessibility parameters.
3. **Property valuation regressor & scenario analyzer** (Random Forest regression with 95% confidence intervals and what-if simulation).
4. **Multimodal transit accessibility bridge** interfacing with Model 3 travel-time networks.

---

## 2. Directory Layout
```
models/model-2-property-valuation/
├── README.md
├── requirements.txt
├── src/
│   ├── real_geo_data.py        # Verified WGS-84 coordinates for localities, metro, IT hubs, highways
│   ├── data_processing.py      # End-to-end dataset builder (Stage A real + Stage B synthetic)
│   ├── valuation_model.py      # Scikit-learn Pipeline, time-consistent split, scenario comparison
│   ├── api.py                  # Flask REST API microservice for property valuation
│   └── accessibility_client.py # Client bridge querying Model 3 transit travel times
├── data/
│   ├── raw/
│   │   └── localities_real.csv # Verified Pune locality metrics & infrastructure scores
│   ├── processed/
│   │   └── master_training_data.csv # Master feature table for ML training (1,260 rows)
│   └── model_checkpoint.joblib # Serialized model checkpoint & validation metrics
├── reports/
│   └── MODEL_2_PROGRESS_AUDIT.md # Comprehensive progress audit report
└── tests/
    └── test_model2.py          # Automated test suite (12 unit and integration tests)
```

---

## 3. Installation & Usage

### Setup
```bash
cd models/model-2-property-valuation
pip install -r requirements.txt
```

### Build / Regenerate Datasets
```bash
python src/data_processing.py
```
This produces:
- `data/raw/localities_real.csv` (Real coordinates, Haversine distances, POI counts, infrastructure score)
- `data/raw/property_history_synthetic.csv` (Documented synthetic micro-market growth)
- `data/processed/properties_synthetic.csv` (Property records)
- `data/processed/master_training_data.csv` (Time-consistent master dataset for model training)

### Run API Microservice
```bash
python src/api.py
```
Starts Flask service on `http://127.0.0.1:5000` (or configured port).

### Run Tests
```bash
pytest tests/test_model2.py -v
```

---

## 4. API Endpoints Specification

| Method | Endpoint | Description | Status |
| :--- | :--- | :--- | :---: |
| `GET` | `/api/v1/health` | Health check, model version, and holdout evaluation metrics | Verified |
| `GET` | `/api/v1/localities` | List verified Pune micro-markets and geospatial anchors | Verified |
| `POST` | `/api/v1/predict` | Predict single property valuation with 95% confidence intervals | Verified |
| `POST` | `/api/v1/compare-scenarios` | Evaluate what-if scenarios (e.g. Metro extension, renovation, area expansion) | Verified |

### Prediction Target & Units
- **Primary Target:** `price` (Total property valuation in Indian Rupees, INR, ₹).
- **Secondary Target:** `price_per_sqft` (Price per square foot, ₹/sq.ft.).
- **Evaluation Strategy:** Strict chronological split (Train: years $\le 2023$, Test: year $2024$) to prevent future lookahead leakage.

---

## 5. Data Provenance & Ethics Specification

This section exists so nobody (including you, a reviewer, or a future contributor) mistakes synthetic data for real transaction records.

### ✅ REAL DATA

| Field | Source | Notes |
|---|---|---|
| `latitude`, `longitude` (locality centroids) | Publicly known locality center coordinates | `src/real_geo_data.py` |
| `distance_to_metro_km` | Haversine calc vs real Pune Metro station coordinates | Computed, not estimated |
| `distance_to_highway_km` | Haversine calc vs real highway reference points | Computed, not estimated |
| `distance_to_it_hub_km` | Haversine calc vs real IT park coordinates (Hinjawadi IT Park, EON Kharadi, Magarpatta) | Computed, not estimated |
| `schools_nearby`, `hospitals_nearby`, `commercial_density` | OpenStreetMap Overpass API (live query attempted first) | **Falls back to a static snapshot table (`FALLBACK_POI_COUNTS` in `data_processing.py`) if no network is available.** That fallback table was derived from a one-time manual Overpass query, not invented. Check `poi_data_source` column in `localities_real.csv` to see which was used for your run. |

### ⚠️ SYNTHETIC DATA (documented formulas, not random noise)

| Field | How it's generated | Why it's not "real" |
|---|---|---|
| `infrastructure_score` | Fixed weighted formula over the REAL fields above (see `compute_infrastructure_score()`) | No standardized public "infrastructure score" metric exists for Indian localities |
| `avg_price_per_sqft` / `price` | Seeded from **directional, publicly-reported broad price ranges** for Pune micro-markets (2019 baseline), then grown using a rate driven by each locality's real `infrastructure_score`, plus small bounded noise | No open, licensed, per-property historical transaction registry exists for Pune |
| `population_growth_pct` | Random within a plausible bounded range (1.0%–4.5%/yr) | No open ward-level annual growth series was integrated in this version |
| `new_projects_count` | Poisson-distributed, scaled by infrastructure score | No open real-time "new projects" registry integrated in this version |
| `property_age_years`, `bedrooms`, `area_sqft` (individual properties) | Randomly distributed within realistic ranges per property type | Individual-property-level open data does not exist publicly |

### Why this design is still meaningful for ML

The synthetic fields are **not random noise disconnected from reality** — price growth is deliberately driven by real geospatial features (distance to metro/IT hub, POI density). This means ML models will learn genuine, explainable relationships between **real location characteristics** and price/growth outcomes. It also means the pipeline is a drop-in replacement target: swap `properties_synthetic.csv` / `property_history_synthetic.csv` for a real licensed dataset later, and everything downstream keeps working.

### To replace with real data later

Provide a CSV with these exact columns and drop it in `data/raw/`:
```csv
locality_name, year, property_type, area_sqft, bedrooms, property_age_years, price, price_per_sqft
```
Then re-run `src/data_processing.py`'s merge stage (Stage C) instead of Stage B's generator.

### Reproducibility

`RANDOM_SEED = 42` is fixed in `data_processing.py` — re-running the script produces identical synthetic data every time.
