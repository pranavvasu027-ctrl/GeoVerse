# GeoVerse Model 1: Step 1 — Labeling Setup Audit & Verification Report

**Audit Date:** October 28, 2026  
**Repository Branch:** `main` (commit `fceba97db29be57afc4e2fea2f73c51363da1596`)  
**Target Module:** `models/model-1-lulc-urban-growth`  
**Repository Path:** `C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\Geoverse`  
**Auditor:** Antigravity Pair-Programming Agent  
**Environment:** Python 3.14.0 (Windows), pytest-9.1.1  
**Scope:** Step 1 Only — Verification of Human Labeling Environment  

---

## 1. Executive Summary & Audit Baseline

This audit evaluates the manual labeling environment for **GeoVerse Model 1 (Historical LULC Classification & Spatio-Temporal Urban Expansion Simulation)**. The objective is to verify whether the local-first labeling application, dataset manifests, historical satellite imagery streaming, schema validation, persistence, and export workflows are verified and safe for human reference annotation.

In strict accordance with the safety instructions:
- **Baseline model training was NOT started.**
- **No human reference labels were fabricated or modified.**
- **Existing uncommitted work was preserved without git reset or clean.**
- **No Supabase connection or migration was initiated.**
- **All fail-closed safeguards and preflight training gates remain active.**

---

## 2. Files Inspected

The following files and components were audited directly against source code and storage on disk:

1. **Application Source Code (`labeling_app/`):**
   - `app.py`: Flask application routes (`/`, `/api/config`, `/api/manifest`, `/api/imagery`, `/api/work_queue`, `/api/qc`, `/api/annotation/<dataset>/<anon_id>`, `/api/export/<dataset>`, `/api/readiness`).
   - `schema.py`: Protocol rules, 5 core land cover classes, 3 abstention classes, date window constraints ($\pm 2$ calendar years), share bins, confidence limits.
   - `storage.py`: Atomic JSON persistence (`t1_annotations.json`, `gold_annotations.json`), collision-resistant timestamped backups in `storage/backups/`.
   - `exporter.py`: Authoritative 35-column CSV export matching `ingest_gold.py` schema, sidecar validation reporting, unmanifested ID tracking.
   - `imagery.py`: Planetary Computer STAC registry for Landsat 5 TM (1991), Landsat 7 ETM+ (2001, 2011), and Landsat 9 OLI-2 (2021).
   - `work_queue.py`: 7-category persistent work queue engine (`work_queue_t1.json`, `work_queue_gold.json`), priority tiers (P1–P5), trajectory anomaly detection.
   - `readiness.py`: 8-gate automated preflight training guard system.
   - `templates/index.html`: Web interface, Leaflet container, multi-epoch synchronized grid, annotation form, QC analytics modal.
   - `static/app.js`: Leaflet orchestration, multi-epoch sync, `Ctrl+S` keyboard shortcuts, unsaved change guards, sample list navigation.
   - `static/style.css`: Workspace layout, GIS controls, contrast-safe styling.
2. **Reference Manifests & Storage Data (`labeling_app/data/`, `labeling_app/storage/`):**
   - `data/t1_manifest.json`: 699 T1 training & tuning sample polygons.
   - `data/gold_manifest.json`: 641 Tier-A Gold evaluation holdout sample polygons.
   - `data/double_interpretation_ids.json`: Authoritative 140 T1 and 160 Gold sample IDs designated for independent review.
   - `storage/t1_annotations.json`: Current live T1 annotations storage (contains 1 partial record: `T2-0002`).
   - `storage/work_queue_t1.json` & `storage/work_queue_gold.json`: Recoverable persistent queue states.
3. **Exports (`labeling_app/exports/`):**
   - `exports/t1_annotated_export.csv`: 699-row wide-format CSV.
   - `exports/t1_annotated_export_validation_report.json`: Sidecar export validation report.
4. **Automated Test Suite (`tests/`):**
   - `tests/test_labeling_app.py`: 35 unit, integration, schema, and safeguard tests.
5. **Project Documentation & Prior Reports:**
   - `README.md`, `requirements.txt`.
   - `reports/MODEL1_DATASET_READINESS_REPORT.md`
   - `reports/MODEL1_HISTORICAL_IMAGERY_AUDIT.md`
   - `reports/MODEL1_DATA_PREPARATION_COMPLETION_REPORT.md`
   - `reports/MODEL1_COMPREHENSIVE_AUDIT_AND_COMPLETION_REPORT.md`

---

## 3. Application Launch & Runtime Verification

- **Launch Command:**
  ```bash
  cd models/model-1-lulc-urban-growth
  python -m labeling_app.app
  ```
- **Access Point:** `http://127.0.0.1:5050`
- **Host & Port:** Bound strictly to local loopback `127.0.0.1` on port `5050`. Does not bind to `0.0.0.0` or expose public network endpoints.
- **Python Environment:** Tested and verified on **Python 3.14.0 (Windows 64-bit)**.
- **Dependencies (`requirements.txt`):**
  - `Flask>=3.0.0` (Installed: Flask 3.1.x)
  - `requests>=2.31.0`
  - `pandas>=2.0.0`
  - `pytest>=8.0.0` (Installed: pytest 9.1.1)
  - `pytest-mock>=3.12.0`
- **Client-Side Assets:** Leaflet 1.9.4 CSS/JS and FontAwesome 6.4.0 loaded via CDN in `templates/index.html`.

---

## 4. Annotation Workflow & Schema Conformance

### 4.1 Supported Land-Cover Classes
The application strictly enforces the project's pre-registered classification schema:

1. **Five Core Definite Classes:**
   - `built_up`: Roof structures, paved surfaces, residential/industrial compounds, transportation corridors.
   - `agriculture`: Cultivated fields, crop parcels, agricultural fallow, orchards.
   - `natural_vegetation`: Dense forest, scrubland, grasslands, riparian corridors.
   - `water`: Reservoirs, rivers, lakes, canals, perennial water bodies.
   - `bare_sparse`: Exposed bedrock, quarries, barren hillsides, dry sediment.
2. **Special Definite Class:**
   - `other`: Requires mandatory descriptive rationale in the `notes` field.
3. **Three Explicit Abstention Classes:**
   - `uncertain`: Usable satellite image exists, but land cover cannot be decisively determined.
   - `ambiguous`: Mixed pixel / heterogeneous transition dispute. Requires mandatory explanation in `notes`.
   - `unavailable`: No cloud-free or usable satellite image exists within $\pm 2$ calendar years of the target epoch.

### 4.2 Area Share & Confidence Constraints
- **Area Share Categories (`dominant_share_3bins`):**
  - `>=75`: Dominant class covers $\ge 75\%$ of the $30\text{ m} \times 30\text{ m}$ cell.
  - `50-75`: Dominant class covers $50\text{--}75\%$ of the cell.
  - `<50`: Dominant class covers $< 50\%$ (heterogeneous mixed pixel).
- **Secondary Class Tracking (`second_class`):**
  - Tracks sub-dominant land cover for mixed pixels. Must be one of the definite classes or `none`, and cannot be identical to the dominant class.
- **Confidence Levels (`confidence_1to3`):**
  - `3`: Unambiguous (high-confidence interpretation).
  - `2`: Likely (plausible interpretation).
  - `1`: Weak (triggers quality warning in work queue).
  - **Landsat Context Rule:** When `imagery_source == "Landsat_context"` ($30\text{ m}$ optical resolution without Very High Resolution aerial photography), confidence is programmatically restricted to $\le 2$.

### 4.3 Date Window Validation
- Imagery dates must fall strictly within $\pm 2$ calendar years of the target epoch:
  - 1990: $[1988\text{--}1992]$
  - 2000: $[1998\text{--}2002]$
  - 2010: $[2008\text{--}2012]$
  - 2020: $[2018\text{--}2022]$

---

## 5. Annotation Format & Downstream Export Schema

### 5.1 Unit of Interpretation
- **Target Unit:** A $30\text{ m} \times 30\text{ m}$ square polygon cell centered at sample coordinates (mean cell span $30.3\text{ m}$).
- The application renders the exact 5-vertex polygon ring dynamically on top of the satellite basemap.

### 5.2 Authoritative 35-Column CSV Export Schema
The export matches the downstream format expected by `src/validation/ingest_gold.py`:
- Columns 1–3: `anon_id`, `lat`, `lon`
- Columns 4–35: Eight attributes across each of the 4 epochs (`[2020, 2000, 2010, 1990]`):
  1. `dominant_class_<epoch>`
  2. `dominant_share_3bins_<epoch>`
  3. `second_class_<epoch>`
  4. `confidence_1to3_<epoch>`
  5. `imagery_source_<epoch>`
  6. `imagery_date_<epoch>`
  7. `status_<epoch>`
  8. `notes_<epoch>`

### 5.3 Export Integrity Safeguards
- Automated backup of previous export CSV and validation report in `exports/backups/`.
- Detection and flagging of unmanifested/orphan sample IDs.
- Deterministic sidecar validation report (`t1_annotated_export_validation_report.json`).

---

## 6. Dataset and Imagery Integrity Findings

### 6.1 Sample Inventory
- **T1 Dataset (`t1_manifest.json`):** 699 sample cells (525 train, 174 tuning). 0 duplicate IDs. All coordinates within PMR ($17.92^\circ\text{--}19.35^\circ\text{ N}$, $73.36^\circ\text{--}75.15^\circ\text{ E}$).
- **Tier-A Gold Dataset (`gold_manifest.json`):** 641 holdout evaluation sample cells (13 strata, 125 spatial blocks). 0 duplicate IDs.
- **Manifest Disjointness:** Strictly disjoint ($699 \cap 641 = \emptyset$).

### 6.2 Existing Annotations Status
- `t1_annotations.json`: Contains 1 partial record (`T2-0002`, 2020 epoch). It was labeled as an exploratory record with `dominant_class: "ambiguous"` and lacks notes, causing 1 schema validation alert in the work queue.
- `gold_annotations.json`: 0 records (`{}`).
- **Verified Human Ground-Truth Progress:** **0 / 1,340 samples completed (0.0%)**.

### 6.3 Historical Imagery Availability
- **Microsoft Planetary Computer STAC:** Live queries return HTTP 200 OK across all four target scenes:
  - 1990: `LT05_L2SP_147047_19911218_02_T1` (Landsat 5 TM, 1991-12-18, 0.0% clouds)
  - 2000: `LE07_L2SP_147047_20011103_02_T1` (Landsat 7 ETM+, 2001-11-03, 0.0% clouds)
  - 2010: `LE07_L2SP_147047_20111217_02_T1` (Landsat 7 ETM+, 2011-12-17, 0.0% clouds)
  - 2020: `LC09_L2SP_147047_20211228_02_T1` (Landsat 9 OLI-2, 2021-12-28, 5.77% clouds)
- **Perimeter Limitation (Documented Workaround):**
  - 37 T1 points and 17 Gold points fall outside Path 147, Row 047.
  - The UI badges these points `[GEP]`. Annotators click "Copy Coords" and inspect the Google Earth Pro historical slider (`GEP_historical`).

---

## 7. Tests Executed and Actual Outcomes

Automated test execution was performed directly via `pytest`:
```bash
pytest tests/test_labeling_app.py -v
```

**Results:** **35 passed in 1.67 seconds** (100% pass rate, 0 failures, 0 warnings).

Full repository regression check:
```bash
pytest models/ -v
```
**Results:** **44 passed in 1.95 seconds** (Model 1: 35 tests, Model 2: 6 tests, Model 3: 3 tests). Zero cross-model regressions.

---

## 8. Verified Fixes Implemented

1. **Double-Interpretation ID Resolution:** Added `labeling_app/data/double_interpretation_ids.json` and updated `work_queue.py` fallback resolution, permanently securing the 140 T1 and 160 Gold dual-review IDs.
2. **Schema Validation Hardening:** Fixed validation bypass on abstain/ambiguous classes in `schema.py`.
3. **Export Integrity Safeguards:** Added unmanifested ID tracking and backup archiving for sidecar validation reports in `exporter.py`.
4. **Work Queue Diagnostic Alerts:** Added explicit schema error alerts in `work_queue.py`.
5. **UI Queue Badging:** Added `[2x]` and `[GEP]` badges and priority filters in `index.html` and `app.js`.
6. **Automated Preflight Training Guards:** Created `labeling_app/readiness.py` and exposed `/api/readiness`.

---

## 9. Known Limitations and Workarounds

1. **Perimeter Points Workaround:** 37 T1 points and 17 Gold points lie on the eastern (Indapur) or western boundaries outside Landsat Path 147, Row 047. Annotators must copy coordinates and inspect Google Earth Pro desktop (`imagery_source: GEP_historical`).
2. **Live Internet Requirement:** In-browser Landsat tiles are fetched dynamically from Microsoft Planetary Computer STAC; active internet connection is required during in-browser labeling.
3. **Existing Partial Record `T2-0002`:** Stored in `t1_annotations.json` with missing notes for `ambiguous`. The human annotator must amend or re-label `T2-0002` during the pilot.
4. **Wall-to-Wall Feature Cube Unbuilt:** `pune_G30.zarr` is absent from local disk. Model training remains fail-closed and strictly blocked.

---

## 10. Human Pilot Labeling Protocol (Step-by-Step)

To conduct a verified, human-supervised pilot labeling batch (e.g., 10–20 samples):

```bash
# 1. Navigate to Model 1 directory
cd models/model-1-lulc-urban-growth

# 2. Verify all preflight tests pass
pytest tests/test_labeling_app.py -v

# 3. Launch the labeling application
python -m labeling_app.app
```

1. Open `http://127.0.0.1:5050` in Google Chrome or Mozilla Firefox.
2. Ensure **Dataset: T1 Training & Tuning (699 points)** is selected.
3. Filter by **Unlabeled** in the sidebar.
4. Select sample `T2-0001` (centered at Lat: 18.14028, Lon: 75.08056) or `T2-0003` (Lat: 18.52041, Lon: 73.85672).
5. Review the $30\text{ m} \times 30\text{ m}$ yellow target boundary across all 4 epochs in sequence (**2020 $\to$ 2000 $\to$ 2010 $\to$ 1990**).
6. For each epoch:
   - Verify active satellite layer: Verified Landsat Collection 2.
   - Choose dominant class from the 5 approved classes (`built_up`, `agriculture`, `natural_vegetation`, `water`, `bare_sparse`).
   - If mixed pixel, select dominant area share ($\ge 75\%$, $50\text{--}75\%$, $<50\%$) and secondary class.
   - Select confidence (3 = unambiguous, 2 = likely, 1 = weak).
   - Press `Ctrl+S` to save.
7. Click **"QC Dashboard"** to verify sample completion and check for trajectory anomalies.
8. Click **"Export CSV"** to generate `t1_annotated_export.csv` and inspect `t1_annotated_export_validation_report.json`.

---

## 11. Final Readiness Decision

### Decision: **READY WITH LIMITATIONS**

**Justification:**
- The labeling application, protocol validation engines, Leaflet spatial viewer, STAC historical satellite imagery streaming, atomic JSON persistence, and 35-column CSV export have been verified and tested (35/35 tests pass).
- The pilot can begin immediately for primary Landsat samples.
- The status is designated as **READY WITH LIMITATIONS** because perimeter points outside Path 147, Row 047 require the documented Google Earth Pro historical slider workaround (`GEP_historical`), live STAC tile streaming requires an active internet connection, and baseline model training remains strictly blocked until all human annotations are complete.

---

## 12. Safety and Integrity Declarations

- [x] **No baseline or confirmatory model training was executed.**
- [x] **No human reference labels were fabricated, generated, or altered.**
- [x] **No mock or synthetic labels were injected into live storage.**
- [x] **All Git working-tree changes and user work have been preserved.**
- [x] **No API keys, credentials, or secrets were exposed.**
