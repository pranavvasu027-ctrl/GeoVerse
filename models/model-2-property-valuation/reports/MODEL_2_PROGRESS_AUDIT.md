# GeoVerse Model 2 — Comprehensive Scientific Progress Audit Report

**Audit Date:** October 21, 2026  
**Auditor:** Senior ML Engineer, Geospatial Data Scientist, & Software Auditor  
**System Target:** GeoVerse AI — Model 2 (Property Value Prediction)  
**Repository Directory:** `C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\GeoVerse\models\model-2-property-valuation`  
**Git Commit:** `dfc8912166f9d7276ba483918c2136190552ccda` (`main` branch)  

---

## 1. Executive Summary

- **Overall Model 2 Completion Score:** **24.0%** (Calculated across the 7 mandated functional categories).
- **Current Development Phase:** **Data Foundation & Geospatial Anchor Preparation** (Implementation Stage: Pre-ML).
- **Has Baseline Training Occurred?** **NO.** No machine learning model fitting routines, estimators, training harnesses, or checkpoint serializations exist in the codebase.
- **Do Valid Performance Metrics Exist?** **NO.** The metrics documented in academic papers and benchmark summaries ($R^2 = 0.77$, $\text{MAE} = 685\text{ \rupee/sq.ft.}$, $\text{MAPE} = 9.4\%$) represent **unverified benchmark calibration targets** (`CLM-09`), not empirical experimental outcomes.
- **Is Model 2 Ready for Integration?** **NO.** Model 2 does not possess a trained model file, an inference pipeline, an API microservice, or spatial joining mechanisms for Model 1 rasters or Model 3 travel-time networks.
- **The Three Most Critical Blockers:**
  1. **Absence of Machine Learning Model Code:** Zero scikit-learn, XGBoost, or LightGBM training loops, feature scalers, categorical encoders, or serialization calls exist.
  2. **100% Synthetic Nature of Property Records:** All 1,260 property records and yearly price trends are generated via deterministic synthetic mathematical formulas seeded by 10 baseline anchors; no real transactional registry records exist.
  3. **Absence of Splitting Logic & Severe Synthetic Target Collinearity:** No train/val/test split exists. Furthermore, in `master_training_data.csv`, `future_price_per_sqft` is a single locality-level average for all properties in that locality and year, which prevents individual hedonic variation from being learned in forward forecasting.

---

## 2. Verified Implementation Inventory

| Component | File Path | Function / Class | Verified What Code Actually Does | Execution Evidence | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **Geospatial Anchors** | `src/real_geo_data.py` | `LOCALITIES`, `METRO_STATIONS`, `IT_HUBS`, `HIGHWAYS` | Defines WGS-84 coordinates for 10 Pune localities, 5 Metro stations, 3 IT hubs, and 3 highway junctions. | Verified in `test_model2.py::test_geo_coordinate_bounds`. | **COMPLETE** |
| **Haversine Distance** | `src/data_processing.py` | `haversine_km(lat1, lon1, lat2, lon2)` | Computes great-circle distance in kilometers using the spherical Haversine formula ($R = 6371\text{ km}$). | Verified in `test_model2.py::test_haversine_properties` (Identity, symmetry, bound checks). | **COMPLETE** |
| **Nearest Distance** | `src/data_processing.py` | `nearest_distance(lat, lon, points_dict)` | Iterates coordinate dictionary and returns `(min_distance_km, nearest_name)`. | Verified in `test_model2.py::test_nearest_distance` (Vanaz station lookup). | **COMPLETE** |
| **OSM POI Fetcher** | `src/data_processing.py` | `fetch_osm_poi_counts()` | Queries live Overpass API for schools, hospitals, and shops within 2 km; falls back to static dictionary on timeout/error. | Fallback table `FALLBACK_POI_COUNTS` verified for all 10 localities. | **COMPLETE** |
| **Locality Table Builder** | `src/data_processing.py` | `build_localities_real()` | Assembles 10-locality tabular dataframe with real coordinates, nearest transit distances, and POI density counts. | Output file `data/raw/localities_real.csv` verified on disk (10 rows, 16 cols). | **COMPLETE** |
| **Infrastructure Scoring** | `src/data_processing.py` | `compute_infrastructure_score(df)` | Weighted formula: $0.30 \times \text{inv\_metro} + 0.25 \times \text{inv\_IT} + 0.20 \times \text{comm} + 0.15 \times \text{amenities} + 0.10 \times \text{inv\_highway}$, scaled 0–100. | Verified in `test_model2.py::test_infrastructure_score_calculation`. | **COMPLETE** |
| **Synthetic Price History** | `src/data_processing.py` | `generate_synthetic_property_history()` | Simulates 2019–2025 yearly locality prices using baseline anchors, infrastructure growth scaling, and $\pm 1.5\%$ noise. | Seeded with `RANDOM_SEED = 42`. Produces consistent 70 history rows. | **IMPLEMENTED (SYNTHETIC)** |
| **Synthetic Property Gen** | `src/data_processing.py` | `generate_synthetic_properties()` | Simulates individual property records (Apartments, Villas, Row Houses) with varying area, bedrooms, age, and type multipliers. | Produces 210 records/year across 10 localities. | **IMPLEMENTED (SYNTHETIC)** |
| **Master Table Merge** | `src/data_processing.py` | `build_master_table()` | Joins property records with localities and historical price trends; computes 1-year forward target `future_price_per_sqft`. | Output file `data/processed/master_training_data.csv` verified (1,260 rows). | **COMPLETE** |
| **Model Regressors** | None | None | No regression classes (LinearRegression, RandomForest, XGBoost, LightGBM) imported or instantiated. | File search in `model-2` returned 0 matches for regressor estimators. | **NOT IMPLEMENTED** |
| **Train/Test Splitting** | None | None | No train/val/test splitting logic (random, chronological, or spatial) implemented. | Zero splitting code found in repository. | **NOT IMPLEMENTED** |
| **Categorical Encoding** | None | None | Strings (`property_type`, `zone`, `nearest_metro_station`) remain unencoded in raw CSV format. | No `OneHotEncoder`, `OrdinalEncoder`, or `pd.get_dummies` pipeline. | **NOT IMPLEMENTED** |
| **Feature Scaler** | None | None | No numerical feature scaling (`StandardScaler`, `MinMaxScaler`) implemented for ML training. | Zero scaling transformations found. | **NOT IMPLEMENTED** |
| **Model Serialization** | None | None | No model saving or loading logic (`joblib.dump()`, `pickle`, `torch.save()`). | 0 checkpoint files (`.joblib`, `.pkl`, `.pt`) found across workspace. | **NOT IMPLEMENTED** |
| **Inference Pipeline** | None | None | No prediction script accepting property input attributes and producing ₹/sq.ft. predictions. | No `predict.py` or inference functions exist. | **NOT IMPLEMENTED** |
| **API Endpoints** | None | None | `Flask` is listed in `requirements.txt`, but no server or routes (`@app.route`) exist for Model 2. | Zero server files in Model 2 directory. | **NOT IMPLEMENTED** |

---

## 3. Data Readiness Report

### Data Readiness Assessment Matrix

| Verification Criterion | Finding & Evidence | Status | Remaining Work |
| :--- | :--- | :---: | :--- |
| **1. Dataset Filenames & Paths** | `data/raw/localities_real.csv` (1,751 B) & `data/processed/master_training_data.csv` (312,692 B). | **COMPLETE** | Maintain versioning and raw/processed separation. |
| **2. Sources & Licensing** | Centroids/Metro/Highways from OpenStreetMap and Maha Metro. Property records are synthetic. | **DOCUMENTED** | License agreement needed if real transactional data is ingested. |
| **3. Available Records** | `localities_real.csv`: 10 rows. `master_training_data.csv`: 1,260 rows (210 rows/yr $\times$ 6 yrs). | **COMPLETE** | Scale to larger sample size when real registry is available. |
| **4. Columns & Data Types** | 30 columns in master table (10 float64, 7 int64, 7 string/object, 6 metadata). | **COMPLETE** | Implement automated schema validation pipeline. |
| **5. Target Variable Definition** | `price_per_sqft` (Current: ₹4,136–₹18,745) and `future_price_per_sqft` (Next yr: ₹5,600–₹14,641). | **COMPLETE** | Address locality-level constant collapse in future price. |
| **6. Missing & Duplicate Records** | 0 null values across all 30 columns. 0 duplicate records. Verified programmatically. | **COMPLETE** | Build imputation safeguards for real-world missing data. |
| **7. Price Plausibility** | Prices span ₹2.1M to ₹61M (Villas up to ₹61M; 1 BHK apartments from ₹2.1M). Plausible for Pune. | **COMPLETE** | Outlier detection thresholds needed for real data. |
| **8. Geographic Coverage** | 10 micro-markets: Hinjawadi, Wakad, Baner, Balewadi, Kharadi, Hadapsar, Viman Nagar, Kothrud, Wagholi, PCMC. | **PARTIALLY COMPLETE** | Add remaining Pune wards/talukas (Aundh, Bavdhan, Shivajinagar, etc.). |
| **9. Temporal Coverage** | 2019 to 2024 (6 years). Exactly 210 records per year. | **COMPLETE** | Incorporate recent post-2024 market data when available. |
| **10. Coordinate Systems & CRS** | WGS-84 (`EPSG:4326`) latitude/longitude floats. Coordinates verified within Pune district. | **PARTIALLY COMPLETE** | Transform into UTM Zone 43N (`EPSG:32643`) for Model 1 alignment. |
| **11. Price Units Consistency** | Standardized strictly to Indian Rupees (INR, ₹) and Square Feet (sq.ft.). | **COMPLETE** | None. Standard is rigorously enforced. |
| **12. Potential Data Leakage** | `future_price_per_sqft` derived deterministically from `infrastructure_score` using fixed formulas. | **AT RISK** | Use chronological train/val splits to prevent equation memorization. |
| **13. Train/Val/Test Splits** | Completely absent. No partitioning logic in codebase. | **NOT IMPLEMENTED** | Implement chronological split (Train $\le 2022$, Val 2023, Test 2024). |
| **14. Real vs. Proxy / Synthetic** | Real geospatial distance anchors; 100% synthetic property transaction records. | **SYNTHETIC PROXY** | Replace with registered property transaction records when available. |

---

## 4. ML Readiness Report

Model 2 contains verified data preparation scripts, but **zero machine learning training, serialization, or inference code**.

1. **Algorithms Evaluated in Code:** **None.** While `xgboost==2.1.1` and `scikit-learn==1.5.1` are pinned in `requirements.txt`, no scripts instantiate `XGBRegressor`, `RandomForestRegressor`, or `LinearRegression`.
2. **Missing Feature Engineering Pipeline:**
   - Categorical columns (`property_type`, `zone`, `nearest_metro_station`, `nearest_highway`, `nearest_it_hub`) remain raw strings.
   - Numerical columns (`area_sqft`, `distance_to_metro_km`, `commercial_density`) have not been normalized or scaled with `StandardScaler`.
3. **Model Checkpoints:** No `.joblib`, `.pkl`, `.pt`, or `.onnx` files exist on disk.
4. **Inference Interface:** No `predict.py` module exists. A caller cannot pass a dictionary of property attributes to obtain a predicted valuation.

---

## 5. Model Evaluation Audit

The academic paper for GeoVerse reports specific performance figures for Model 2 (Table V and Section VI-C). Our empirical audit investigated whether these metrics were derived from codebase execution:

| Evaluation Metric | Reported in Paper | Verified Codebase Status | Supporting Evidence on Disk |
| :--- | :---: | :---: | :--- |
| **Mean Absolute Error (MAE)** | $685\text{ \rupee/sq.ft.}$ | **UNVERIFIED / BENCHMARK TARGET** | No evaluation logs, prediction CSVs, or metric calculation scripts found (`CLM-09`). |
| **Root Mean Squared Error (RMSE)** | $1050\text{ \rupee/sq.ft.}$ | **UNVERIFIED / BENCHMARK TARGET** | No evaluation code exists (`CLM-09`). |
| **Coefficient of Determination ($R^2$)** | $0.77$ | **UNVERIFIED / BENCHMARK TARGET** | No regression fit exists (`CLM-09`). |
| **Mean Absolute Percentage Error (MAPE)** | $9.4\%$ | **UNVERIFIED / BENCHMARK TARGET** | No metric script exists (`CLM-09`). |
| **Model 1 Growth Ablation Benefit** | $9.9\%$ error reduction ($\Delta\text{MAE} = -75$) | **UNVERIFIED / BENCHMARK TARGET** | No controlled ablation script exists (`CLM-10`). |

**Auditor Conclusion:** Model performance remains **untested and unverified**. All cited metrics represent aspirational benchmark targets.

---

## 6. Integration Audit

### 1. Model 1 (Urban Growth) $\rightarrow$ Model 2 Integration
- **Upstream Prediction Availability:** **BLOCKED.** Model 1 confirmatory experiments C1–C6 are fail-closed (`DO NOT RUN`). No predicted urban growth raster (`.tif`) exists.
- **Coordinate Reference System Incompatibility:** Model 1 operates on a $6,546 \times 5,624$ raster grid in UTM Zone 43N (`EPSG:32643`). Model 2 stores coordinates in WGS-84 (`EPSG:4326`). Spatial reprojection is required.
- **Missing Spatial Join:** Model 2 has no GIS raster-sampling code (`rasterio.sample` or `geopandas.sjoin`) to extract growth probabilities at property coordinates.
- **Temporal Leakage Safeguard:** Model 1 epochs are 1990, 2000, 2010, and 2020. Model 2 property records span 2019–2024. When training on 2019–2020 data, Model 2 must only ingest growth features from $\le 2020$.

### 2. Model 2 $\rightarrow$ Model 3 (Accessibility) Compatibility
- **Current State:** Model 2 computes straight-line Haversine distances to 5 metro stations.
- **Potential:** Model 3 possesses a custom C++ routing engine with 63 nodes and real transit times/costs across Pune/PCMC. Refactoring Model 3 to serve transit travel times (`travel_time_to_cbd_mins`, `nearest_metro_dist_km`) to Model 2 would replace Euclidean distances with network travel times.
- **Current Interface:** **ABSENT.** No programmatic bridge exists between Model 2 and Model 3.

---

## 7. Software Quality & Test Results

### Automated Unit Test Run
The test suite in `models/model-2-property-valuation/tests/test_model2.py` was executed:

```powershell
pytest "models/model-2-property-valuation/tests/test_model2.py" -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI
collected 6 items

models/model-2-property-valuation/tests/test_model2.py::test_haversine_properties PASSED [ 16%]
models/model-2-property-valuation/tests/test_model2.py::test_geo_coordinate_bounds PASSED [ 33%]
models/model-2-property-valuation/tests/test_model2.py::test_nearest_distance PASSED [ 50%]
models/model-2-property-valuation/tests/test_model2.py::test_infrastructure_score_calculation PASSED [ 66%]
models/model-2-property-valuation/tests/test_model2.py::test_localities_real_csv_integrity PASSED [ 83%]
models/model-2-property-valuation/tests/test_model2.py::test_master_training_data_schema PASSED [100%]

============================== 6 passed in 0.79s ==============================
```

- **Passed:** 6 tests.
- **Failed:** 0 tests.
- **Coverage Limitations:** Tests cover only mathematical distance calculations, locality boundary assertions, and CSV schema integrity. Zero tests exist for machine learning models, categorical encoders, scalers, or inference endpoints.

---

## 8. Quantitative Completion Scoring

| Evaluation Component | Weight | Criteria & Implementation Evidence | Evaluated Status | Score (%) | Weighted Progress |
| :--- | :---: | :--- | :---: | :---: | :---: |
| **1. Data collection & readiness** | 20% | 10 real locality anchors verified; 1,260-row master CSV exists. Property records are 100% synthetic; target formulation has locality-constant collapse. | Partially complete | **35%** | 7.0% |
| **2. Preprocessing & feature engineering** | 15% | Haversine distance math, nearest transit resolution, and infrastructure scoring formulas implemented and unit-tested. Categorical encoding and feature scalers are absent. | Partially complete | **50%** | 7.5% |
| **3. ML pipeline & training readiness** | 20% | Packages listed in `requirements.txt`. Zero training scripts, model classes, hyperparameter configs, or serialization routines exist. | Not implemented | **5%** | 1.0% |
| **4. Evaluation & scientific validation** | 15% | Zero evaluation code, metric functions, or backtesting scripts exist. Paper metrics are unverified benchmark calibration targets. | Not implemented | **0%** | 0.0% |
| **5. Model 1 integration readiness** | 10% | Conceptual architecture documented in papers. Zero raster sampling code, CRS conversion, or ablation scripts exist. Upstream rasters are ungenerated. | Not implemented | **10%** | 1.0% |
| **6. API, output schema, & compatibility** | 10% | Target units (₹/sq.ft.) and locality attributes established in CSV schema. Zero REST APIs, inference endpoints, or database connections exist. | Not implemented | **15%** | 1.5% |
| **7. Testing & documentation** | 10% | Comprehensive `README.md` documenting provenance and formulas. 6 unit tests passing with zero failures. GitHub Actions CI configured. Missing ML and API tests. | Partially complete | **60%** | 6.0% |
| **Total** | **100%** | | | | **24.0%** |

---

## 9. Remaining Work Breakdown

```
Phase 1: Feature Pipeline & Splitting
   ├── ColumnTransformer Pipeline (OneHotEncoder + StandardScaler)
   └── Leakage-Free Chronological Splitter (Train <= 2022, Val 2023, Test 2024)
              │
              ▼
Phase 2: Baseline Model Training & Persistence
   ├── Baseline Regressors (Ridge + XGBoost in src/train.py)
   └── Model Serialization (checkpoints/model_v1.joblib)
              │
              ▼
Phase 3: Validation, SHAP & Serving
   ├── Evaluation Metrics (MAE, RMSE, R², MAPE in src/evaluate.py)
   ├── SHAP Feature Explainer (src/explain.py)
   └── Standalone Inference Interface (src/predict.py)
```

### 1. Critical Blockers (Required before any model training)
- **Task 1.1: Build Preprocessing Pipeline (`src/features.py`):** Author a scikit-learn `ColumnTransformer` handling categorical encoding (`OneHotEncoder`) and numeric scaling (`StandardScaler`).
- **Task 1.2: Implement Leakage-Free Train/Val/Test Splitter:** Create chronological partition (Train: 2019–2022, Val: 2023, Test: 2024) and spatial leave-one-locality-out partition.

### 2. Required Before Baseline Training
- **Task 2.1: Implement Baseline & Gradient Boosting Training Script (`src/train.py`):** Train Ridge regression (baseline) and XGBoost Regressor (`XGBRegressor`) on the processed feature matrix.
- **Task 2.2: Implement Model Serialization:** Serialize trained estimators and fitted preprocessing pipelines to `models/model-2-property-valuation/checkpoints/model_v1.joblib`.

### 3. Required Before Model Validation
- **Task 3.1: Implement Evaluation & Metric Reporting (`src/evaluate.py`):** Compute MAE, RMSE, $R^2$, and MAPE on the holdout test set with residual diagnostics.
- **Task 3.2: Implement SHAP Feature Attribution (`src/explain.py`):** Compute SHAP TreeExplainer values to verify whether geospatial distance features genuinely drive price variations.

### 4. Required Before Model 1 Integration
- **Task 4.1: Implement Geospatial Raster Sampling Bridge:** Reproject property coordinates to UTM Zone 43N (`EPSG:32643`) and extract cell growth probabilities from Model 1 rasters.
- **Task 4.2: Execute Growth Feature Ablation Experiment:** Measure the exact $\Delta\text{MAE}$ and $\Delta R^2$ when including vs. excluding urban growth features.

### 5. Required Before System Integration
- **Task 5.1: Build Standalone Inference Module (`src/predict.py`):** Callable inference function taking property dictionary $\rightarrow$ predicted ₹/sq.ft. and total price.
- **Task 5.2: Build Model 2 Microservice (`src/server.py`):** Expose `/api/v1/predict/valuation` REST endpoint with input validation.

---

## 10. Next-Step Recommendation

**Recommended Action:** **Implement the Preprocessing Pipeline and Baseline Training Script (`src/features.py` and `src/train.py`).**

**Justification:**
Model 2 already possesses a verified, clean 1,260-row master feature table (`master_training_data.csv`) and verified real geospatial anchors (`localities_real.csv`). The primary bottleneck preventing Model 2 from functioning as an operational ML system is the total absence of training code. Building `src/features.py` (with categorical encoding and scaling) and `src/train.py` (fitting Ridge and XGBoost models with a chronological train/test split) will transform Model 2 into an active, verifiable ML model with genuine checkpoints and measurable performance metrics.

---

## 11. Final Decision

# **"NOT READY FOR BASELINE TRAINING"**

### Supporting Evidence:
1. **Zero Model Fitting Code:** No machine learning training script exists in the repository.
2. **Missing Feature Pipeline:** Categorical variables (`property_type`, `zone`) remain unencoded raw strings; no preprocessing or numerical scaling exists.
3. **No Splitting Logic:** No train/validation/test partitions exist to prevent data leakage.
4. **Target Variable Redundancy:** In the current master dataset, `future_price_per_sqft` is a single locality-level constant for all properties in a given year, which would cause an uncalibrated model to fit only locality means rather than individual property hedonic valuations.
5. **Prerequisites for "READY FOR BASELINE TRAINING":** Model 2 will achieve "READY FOR BASELINE TRAINING" as soon as a `ColumnTransformer` feature pipeline, a chronological train/test splitter, and a verified `train.py` script are authored.
