# Model 1: LULC Classification & Spatio-Temporal Urban Growth Analysis

## 1. Overview
Model 1 provides Earth Observation (EO) satellite remote sensing, multi-decadal Land Use / Land Cover (LULC) classification, and spatio-temporal urban expansion modeling for the Pune Metropolitan Region (PMR) across a $30\text{ m} \times 30\text{ m}$ spatial resolution ($6,546 \times 5,624$ lattice in UTM Zone 43N / `EPSG:32643`).

The target analytical timeline spans four primary epochs: **1990, 2000, 2010, and 2020** (utilizing Landsat 5 TM, Landsat 7 ETM+, Landsat 8 OLI, Sentinel-1 SAR, and Copernicus GLO-30 DEM terrain data).

---

## 2. Directory Structure
```
models/model-1-lulc-urban-growth/
├── README.md
├── requirements.txt
├── labeling_app/
│   ├── app.py                     # Flask web labeling tool entrypoint
│   ├── schema.py                  # Protocol v2 validation rules & schema guards
│   ├── storage.py                 # Atomic JSON persistence & backup manager
│   ├── qc.py                      # Multi-rater agreement & anomaly detection
│   ├── exporter.py                # 35-column ingest_gold schema exporter
│   ├── imagery.py                 # Planetary Computer STAC tile resolution
│   ├── work_queue.py              # 7-category persistent work queue manager
│   ├── readiness.py               # Preflight training guard & fail-closed checklist
│   ├── data/
│   │   ├── double_interpretation_ids.json # 140 T1 and 160 Gold double-interpretation IDs
│   │   ├── gold_manifest.json     # 641 Tier-A Gold evaluation sample polygons
│   │   └── t1_manifest.json       # 699 T1 training/tuning sample polygons
│   ├── storage/
│   │   ├── t1_annotations.json    # Live persistent T1 annotations
│   │   ├── work_queue_gold.json   # Persistent work queue state (Gold)
│   │   └── work_queue_t1.json     # Persistent work queue state (T1)
│   ├── exports/                   # 35-column CSV exports and sidecar validation reports
│   ├── static/                    # Leaflet JS map viewer and styling
│   └── templates/                 # Browser UI template
├── reports/                       # Scientific readiness and audit reports
└── tests/
    └── test_labeling_app.py       # 35 automated unit, schema, and safeguard tests
```

---

## 3. Reference Datasets & Strict Separation
Model 1 strictly enforces separation between training data and evaluation reference data:

1. **T1 Training & Tuning Dataset (699 samples):**
   - 525 training / 174 hyperparameter tuning points.
   - Used to train exploratory and confirmatory classification models.
2. **Tier-A Gold Evaluation Dataset (641 samples):**
   - Stratified across 13 strata and 125 spatial blocks across Pune District.
   - Evaluator-only holdout dataset. **Protected evaluator keys and ground-truth labels are strictly excluded from public version control.**

---

## 4. Current Scientific Readiness & Status
- **Labeling Tool & QC Infrastructure:** **100% OPERATIONAL & VERIFIED** (35 automated tests pass).
- **Automated Preflight Guards:** **ACTIVE & FAIL-CLOSED** (Verifies human labels, feature cube, export reconciliation, and user approval).
- **Persistent Work Queues:** **OPERATIONAL** (Tracks unannotated, partial, suitable imagery, unavailable imagery, low confidence, independent review, and inconsistent records).
- **Human Visual Reference Annotations:** **0 / 1,340 Completed (0.0%)**.
  - Current storage contains 1 unverified partial 2020 record (`T2-0002`) and 0 Gold records.
  - Per protocol v2, human reference interpretation must be performed by human interpreters before training begins.
- **District Zarr Feature Cube:** **NOT BUILT LOCALLY** (Requires remote high-memory compute run).
- **Confirmatory Experiments (C1–C6):** **FAIL-CLOSED (`DO NOT RUN`)**.
  - Model training is intentionally blocked by automated guards until authentic human reference labels are supplied.

---

## 5. Running the In-Browser Labeling Application

### Setup
```bash
cd models/model-1-lulc-urban-growth
pip install -r requirements.txt
```

### Launch
```bash
python -m labeling_app.app
```
Access the application at `http://127.0.0.1:5050` in your web browser.

### Key Functionality:
- **Spatial Viewer:** Dual-layer OpenStreetMap / Sentinel-2 RGB mosaic with $30\text{ m} \times 30\text{ m}$ sample polygon overlay.
- **Protocol Enforcement:** 5 standard classes (`built_up`, `agriculture`, `natural_vegetation`, `water`, `bare_sparse`), 3 area share bins, secondary class tracking, and date-window validation ($\pm 2$ calendar years).
- **Work Queue Navigation:** Next-unlabeled button, priority filters, and double-interpretation routing.

---

## 6. Running Automated Tests
```bash
cd models/model-1-lulc-urban-growth
pytest tests/test_labeling_app.py -v
```
All 35 test cases test:
- Annotation validation & schema conformance (definite and abstain classes)
- Invalid category rejection and confidence restrictions
- Landsat context confidence caps (max 2)
- Atomic storage, reload, and automated backup creation
- Ingestion schema compatibility (35 columns) and unmanifested ID detection
- Authoritative double-interpretation resolution (140 T1, 160 Gold)
- Spatial polygon integrity and PMR bounds checking (1,340 samples)
- QC analytics and trajectory anomaly detection
- Inter-rater agreement statistics (Cohen's Kappa & % concordance)
- Persistent work queue recovery, category coverage, and action guidance
- Gold dataset API integration and export workflows
- Fail-closed automated training preflight guards (refuses unauthorized execution)

---

## 7. Running Preflight Training Readiness Check
```bash
cd models/model-1-lulc-urban-growth
python -m labeling_app.readiness
```
Prints the structured 8-gate readiness audit. Fails closed (`BLOCKED`) if authentic human labels, feature cubes, or explicit approvals are absent.
