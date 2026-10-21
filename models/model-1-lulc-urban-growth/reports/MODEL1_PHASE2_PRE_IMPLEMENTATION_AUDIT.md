# Model 1 Phase 2: Pre-Implementation Audit Report

**Audit Date:** October 20, 2026  
**Auditor:** Antigravity Pair-Programming Agent  
**Repository Path:** `C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\GeoVerse\lulc-p1-p6`  
**Active Git Branch:** `main` (commit `be976a9620af13ef133c196b20e7172361936dc9`, working tree clean)  
**Strict Focus:** GeoVerse Model 1 ONLY (LULC Classification and Urban Growth Analysis). Model 2, Model 3, and cross-model integrations are strictly excluded.

---

## 1. Verified Facts vs. Unverified Claims

### 1.1 Verified Dataset Facts
1. **Gold Evaluation Dataset:**
   - Total sample count: **641 unique samples** (`P4-0001` through `P4-0641`).
   - Stratification: 13 strata, 125 spatial blocks across 3 climatic regions.
   - Double-interpretation subset: 160 samples assigned to Interpreter B.
   - Status: **0 / 641 completed human annotations**.
   - Template: `gold_form_interpreter_A.csv` exists inside `phase6/data/phase6_gold_kit_INTERPRETER_A.zip` (35 columns, completely empty of labels).
   - Geometry: Exact $30\text{ m} \times 30\text{ m}$ cell polygons exist in `gold_cells_interpreter_A.kml` for all 641 points.
2. **T1 Training Dataset:**
   - Total sample count: **699 unique samples** (`T2-0001` through `T2-0699`).
   - Partitioning: 525 `train` points and 174 `tuning` points.
   - Double-interpretation subset: 140 samples assigned to Interpreter B.
   - Status: **0 / 699 completed human annotations**.
   - Template: `T1v2_form_interpreter_A.csv` exists inside `phase6/data/phase6_T1v2_kit_INTERPRETER_A.zip` (35 columns, completely empty of labels).
   - Geometry: Exact $30\text{ m} \times 30\text{ m}$ cell polygons exist in `T1v2_cells_interpreter_A.kml` for all 699 points.
3. **Harmonization & Test Rigor:**
   - 217 automated tests pass on synthetic mocks; `c2_tm_pif_v1` transform is frozen.
   - C1–C6 confirmatory experiments are strictly blocked by fail-closed guards (`Refusal: DO NOT RUN`) until human labels are supplied.

### 1.2 Unverified / External Claims
- **District Feature Cubes on Local Disk:** The 95.3 GB full-district satellite composites and dual 24.7 GB Zarr cubes are **not** present in the local laptop directory (they were processed in an external cloud environment). Only exploratory window samples exist on disk.
- **In-Browser Historical Satellite Imagery:** Standard web basemaps (OSM, ESRI World Imagery) only provide contemporary (present-day) imagery. Direct tile-server integration for historical years (1990, 2000, 2010) does **not** exist locally.

---

## 2. Annotation Schema & Ingestion Protocol Verification

From `src/validation/ingest_gold.py` and `INTERPRETER_PROTOCOL.md`, the authoritative schema rules are:

### 2.1 Target Epochs & Inspection Sequence
- Epoch order: **2020 $\rightarrow$ 2000 $\rightarrow$ 2010 $\rightarrow$ 1990**.
- Allowable image window: $\pm 2$ calendar years around the target epoch.

### 2.2 Controlled Vocabularies
- **`dominant_class` (5 Core Definite + Other + 3 Abstain):**
  - `built_up`
  - `agriculture`
  - `natural_vegetation`
  - `water`
  - `bare_sparse`
  - `other` (requires explanation in `notes`)
  - `uncertain` (image exists but cannot decide)
  - `ambiguous` (mixed pixel / transition dispute)
  - `unavailable` (no usable image within $\pm 2$ years)
- **`dominant_share_3bins`:** `>=75`, `50-75`, `<50`
- **`second_class`:** `none`, or one of `built_up`, `agriculture`, `natural_vegetation`, `water`, `bare_sparse`, `other` (must not equal `dominant_class`).
- **`confidence_1to3`:** `3` (unambiguous), `2` (likely), `1` (weak).
- **`imagery_source`:** `GEP_historical`, `Landsat_context`, `field`, `Sentinel2_context`, `other_vhr`.  
  *(Forbidden sources rejected by validator: any AI, model, or consensus product like WorldCover, Esri, Dynamic World).*
- **`imagery_date`:** ISO format (`YYYY-MM-DD`). Calendar year must strictly fall in $[\text{epoch}-2, \text{epoch}+2]$.
- **`status`:** `done`, `unavailable`, `skipped`, or `""`.

---

## 3. Security & Gold Evaluation Data Protection

1. **Sensitive File:** `phase6/data/phase6_KEYS_evaluator_only.zip` contains evaluator-only design metadata (sampling probabilities, stratum boundaries, and secret test keys).
2. **Access Control Safeguards:**
   - The labeling application must run locally on `127.0.0.1` and never serve `phase6_KEYS_evaluator_only.zip` via HTTP.
   - Evaluator-only keys and design columns must **never** be injected into HTML or client-side JavaScript.
   - The labeling app will consume only the authorized interpreter kits (`gold_form_interpreter_A.csv` and `T1v2_form_interpreter_A.csv`) and their respective KML cell geometries.
   - Gold evaluation data and T1 training data will be strictly segregated by dataset selection modes.

---

## 4. Implementation Approach for Phase 2

1. **Architecture:** A lightweight, dependency-free local Python Flask server + Leaflet.js single-page application.
2. **Persistence Strategy:**
   - Maintain a local working JSON storage (`data/labeling_store/`) with atomic writes, auto-save, and timestamped backups.
   - Provide an export utility generating the exact CSV schema (`anon_id`, `lat`, `lon`, and 32 epoch-specific columns) directly compatible with `src/validation/ingest_gold.py`.
3. **Historical Imagery Disclosure:**
   - Clearly label the Leaflet map as **"Present-day Reference Context"**.
   - Prominently display the notice: *"Historical imagery (1990/2000/2010) is not served directly in this viewer. Consult Google Earth Pro historical slider or Landsat archives."*
   - Provide one-click coordinate copying to paste into Google Earth Pro or GIS tools.
4. **AI Assistance Segregation:**
   - Include a segregated placeholder panel with a distinct color, clearly tagged *"AI Suggested Context (Experimental - Unverified)"*.
   - Never auto-fill or auto-commit AI suggestions as human labels.
