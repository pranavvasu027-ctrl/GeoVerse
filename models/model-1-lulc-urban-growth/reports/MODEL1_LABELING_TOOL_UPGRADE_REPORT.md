# GeoVerse Model 1: Historical LULC Labeling Tool Upgrade Report

**Document Date:** October 2026  
**Project:** GeoVerse — Model 1 (Historical LULC Classification & Urban Growth)  
**Target Directory:** `C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\GeoVerse\lulc-p1-p6`  
**Host & Port:** `http://127.0.0.1:5050`  

---

## 1. Executive Summary

In accordance with strict scientific boundaries for **GeoVerse Model 1 Only**, the local-first Human-in-the-Loop Historical LULC Labeling Application has been systematically audited, preserved, and upgraded. No code or files associated with Model 2 (Property Valuation), Model 3 (`Smart-root-optimizer`), or unified dashboards were modified.

The upgrade delivers an advanced, protocol-compliant visual interpretation workspace. It resolves the core challenge of historical inspection by integrating verified **USGS Landsat Collection 2 Level-2 Surface Reflectance** tile layers via Microsoft Planetary Computer STAC for 1990, 2000, 2010, and 2020. Annotators are equipped with precise spatial controls ($30\text{ m}$ target boundary, neighborhood context zoom, coordinate copy), an optional **synchronized 4-epoch comparative grid**, keyboard shortcuts (`Ctrl+S`), unsaved changes warnings, a real-time **trajectory consistency assistant**, and a comprehensive **Quality-Control (QC) analytics modal**.

---

## 2. Before-and-After Implementation Audit

| Component | Initial Baseline | Upgraded Implementation |
|---|---|---|
| **Spatial Viewer** | Static Leaflet map with standard zoom controls; $30\text{ m}$ cell drawn as simple polygon without cell snap. | Interactive viewer with **"Zoom to Cell (30m)"** (z18), **"Neighborhood Context (500m)"** (z15), toggleable bounding box, and center crosshair. |
| **Historical Imagery** | Modern basemap disclaimer only; no authentic historical satellite tiles integrated in Leaflet. | **Verified Landsat Collection 2 Tier-1 Level-2** tile layers dynamically loaded for 1990, 2000, 2010, and 2020 via Microsoft Planetary Computer STAC. |
| **Multi-Epoch Inspection** | Single-epoch dropdown view; reviewer had to switch epochs sequentially to compare years. | **Synchronized 4-Panel Multi-Epoch Grid** (1990, 2000, 2010, 2020 side-by-side) with shared pan/zoom around the $30\text{ m}$ cell. |
| **Annotation Speed** | Form submission required scrolling and manual button click; navigation could drop unsaved edits. | **`Ctrl+S` / `Cmd+S` keyboard shortcuts**, button hotkeys, and **unsaved changes guard** (`beforeunload` & switch prompt). |
| **Temporal Trajectory** | None; annotator had no immediate context of other epoch decisions for the same sample. | **Real-Time Trajectory Assistant Card** showing sequence ($T_{1990} \to T_{2000} \to T_{2010} \to T_{2020}$) and flagging potential urban reversion anomalies. |
| **Quality Control (QC)** | Progress percentage bar only (samples with 4 epochs completed). | **Live QC Dashboard Modal** tracking sample completion, per-epoch counts, low confidence distribution, cloud/shadow issues, and anomalies. |
| **Automated Testing** | 8 baseline unit/integration tests covering validation and storage. | **15 rigorous automated tests** covering validation, storage, Landsat imagery resolution, QC analytics, and REST API flows. |

---

## 3. Verified Historical Satellite Imagery Infrastructure

All historical satellite scenes were verified against the USGS Landsat archive for Pune District (**Path 147, Row 047**) via the Planetary Computer STAC catalog:

1. **Epoch 1990 (Landsat 5 TM):**
   - **Scene ID:** `LT05_L2SP_147047_19911218_02_T1`
   - **Acquisition Date:** 1991-12-18 (Within protocol window: 1988–1992)
   - **Cloud Cover:** 0.00%
   - **Bands / Colormap:** True-color RGB (Bands 3, 2, 1)
   - **Sensor Health:** Functional TM sensor; no scan-line anomalies.

2. **Epoch 2000 (Landsat 7 ETM+):**
   - **Scene ID:** `LE07_L2SP_147047_20011103_02_T1`
   - **Acquisition Date:** 2001-11-03 (Within protocol window: 1998–2002)
   - **Cloud Cover:** 0.00%
   - **Bands / Colormap:** True-color RGB (Bands 3, 2, 1)
   - **Sensor Health:** Pre-SLC-off (Acquired prior to May 2003 failure; 100% data coverage).

3. **Epoch 2010 (Landsat 7 ETM+):**
   - **Scene ID:** `LE07_L2SP_147047_20111217_02_T1`
   - **Acquisition Date:** 2011-12-17 (Within protocol window: 2008–2012)
   - **Cloud Cover:** 0.00%
   - **Bands / Colormap:** True-color RGB (Bands 3, 2, 1)
   - **Sensor Health:** SLC-off composite; cloud-free post-monsoon acquisition.

4. **Epoch 2020 (Landsat 9 OLI-2):**
   - **Scene ID:** `LC09_L2SP_147047_20211228_02_T1`
   - **Acquisition Date:** 2021-12-28 (Within protocol window: 2018–2022)
   - **Cloud Cover:** 0.00%
   - **Bands / Colormap:** True-color RGB (Bands 4, 3, 2)
   - **Sensor Health:** 14-bit radiometric resolution, optimal signal-to-noise.

Detailed scene metadata and tile endpoints are documented in `MODEL1_HISTORICAL_IMAGERY_AUDIT.md` and served by `labeling_app/imagery.py`.

---

## 4. Upgraded Architecture & Source Code

The upgraded application files reside in `lulc-p1-p6/labeling_app/`:

```
labeling_app/
├── __init__.py
├── app.py                # Flask routes: /api/manifest, /api/annotations, /api/imagery, /api/qc, /export
├── validation.py         # Protocol rules (classes, shares, date window, confidence constraints)
├── storage.py            # Atomic JSON writes, schema validation, timestamped backups
├── manifests.py          # Strict isolation between Gold (641) and T1 (699) manifests
├── imagery.py            # STAC scene registry & Planetary Computer dynamic tile endpoints
├── qc.py                 # Real-time QC metrics, audit summaries, trajectory anomaly detection
├── templates/
│   └── index.html        # Leaflet workspace, multi-epoch grid, controls, trajectory card, QC modal
└── static/
    ├── style.css         # Responsive styling for GIS controls, comparison panels, badges
    └── app.js            # Leaflet orchestration, multi-map syncing, keyboard shortcuts, unsaved guards
```

---

## 5. Automated Test Suite Results

Test execution was performed using `pytest` from the `lulc-p1-p6` root directory:

```bash
python -m pytest tests/test_labeling_app.py -v
```

**Results:**
```
tests/test_labeling_app.py::test_valid_annotation PASSED                 [  6%]
tests/test_labeling_app.py::test_invalid_category_rejection PASSED       [ 13%]
tests/test_labeling_app.py::test_missing_mandatory_field PASSED          [ 20%]
tests/test_labeling_app.py::test_other_requires_notes PASSED             [ 26%]
tests/test_labeling_app.py::test_date_window_validation PASSED           [ 33%]
tests/test_labeling_app.py::test_landsat_context_max_confidence PASSED   [ 40%]
tests/test_labeling_app.py::test_storage_save_reload_and_backup PASSED   [ 46%]
tests/test_labeling_app.py::test_export_schema_compatibility PASSED      [ 53%]
tests/test_labeling_app.py::test_historical_imagery_resolution PASSED    [ 60%]
tests/test_labeling_app.py::test_qc_analytics_computation PASSED         [ 66%]
tests/test_labeling_app.py::test_app_startup_and_config PASSED           [ 73%]
tests/test_labeling_app.py::test_imagery_endpoint PASSED                 [ 80%]
tests/test_labeling_app.py::test_qc_endpoint PASSED                      [ 86%]
tests/test_labeling_app.py::test_manifest_endpoint PASSED                [ 93%]
tests/test_labeling_app.py::test_save_and_retrieve_annotation_flow PASSED [100%]

======================= 15 passed in 1.55s =======================
```

---

## 6. Scientific Integrity & Data Safety Verification

1. **Evaluator Isolation Preserved:** The private gold evaluation key (`phase6_KEYS_evaluator_only.zip`) was not opened, modified, or exposed.
2. **Gold vs T1 Isolation:** Annotations for Gold (`gold_annotations.json`) and T1 (`t1_annotations.json`) remain in independent, strictly segregated stores.
3. **Downstream Compatibility:** All exported CSV records match the 35-column schema required by `src/validation/ingest_gold.py`.
4. **Honest Imagery Reporting:** No modern basemap is ever represented as historical data. When Landsat context is used without VHR, confidence is programmatically restricted to $\le 2$ as mandated by the registered protocol.
