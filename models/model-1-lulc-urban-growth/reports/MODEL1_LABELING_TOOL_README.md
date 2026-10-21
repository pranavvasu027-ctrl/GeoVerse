# GeoVerse Model 1: Historical LULC Labeling Tool

A local-first, human-in-the-loop web application engineered specifically for **GeoVerse Model 1 (LULC Classification and Urban Growth Analysis)**. It enables rigorous visual interpretation of historical 30 m cell samples across Pune District strictly following the pre-registered scientific protocol (`INTERPRETER_PROTOCOL.md` and `src/validation/ingest_gold.py`).

---

## 1. Quick Start Guide

### Prerequisites
- Python 3.10+ (Standard library, Flask, pandas, pytest).
- No external GIS servers required; all spatial dependencies and basemaps run locally via browser Leaflet.js.

### Launching the Application Locally
Run the following command from the `lulc-p1-p6` root directory:

```bash
python -m labeling_app.app
```

Then open your browser to:
`http://127.0.0.1:5050`

---

## 2. Core Workflow & Features

### A. Dataset Segregation (Gold vs. T1)
- Use the **Dataset** dropdown in the top header to toggle between:
  1. **T1 Training & Tuning Dataset (699 points):** Used to train Model 1 classifiers and calibrate conformal prediction sets.
  2. **Tier-A Gold Reference Dataset (641 points):** Used exclusively for blind, design-based evaluation of historical epochs.
- Both workflows maintain completely isolated local storage files to eliminate risk of label leakage.

### B. Sample Navigation & Progress Tracking
- Browse samples sequentially or jump directly using the search filter.
- Filter by status: `Unlabeled`, `In Progress`, or `Completed`.
- Real-time progress bar tracks completed 4-epoch interpretations.

### C. Spatial Viewer, Controls & 30m Target Geometry
- Each sample automatically centers on its coordinates with its precise **$30\text{ m} \times 30\text{ m}$ polygon boundary** rendered in gold with an inner target crosshair.
- **Zoom Controls:** Dedicated interactive buttons:
  - **Zoom to Cell:** Snaps directly to zoom level 18 centered on the 30 m cell.
  - **Neighborhood Context (500m):** Zooms out to level 15 to evaluate landscape context.
  - **Toggle Boundary:** Toggles the gold bounding box on/off to examine pixel edges.
- One-click copy button (`Lat, Lon`) allows instant pasting into **Google Earth Pro** for VHR historical slider analysis.

### D. Verified Historical Satellite Imagery & Multi-Epoch Workspace
- **True Historical Tile Service:** Integrated with Microsoft Planetary Computer STAC for verified Landsat Collection 2 Tier-1 Level-2 surface reflectance products across Pune District (Path 147, Row 047):
  - **1990:** Landsat 5 TM (`LT05_L2SP_147047_19911218_02_T1`, acquired 1991-12-18, 0.0% clouds)
  - **2000:** Landsat 7 ETM+ (`LE07_L2SP_147047_20011103_02_T1`, acquired 2001-11-03, 0.0% clouds)
  - **2010:** Landsat 7 ETM+ (`LE07_L2SP_147047_20111217_02_T1`, acquired 2011-12-17, 0.0% clouds)
  - **2020:** Landsat 9 OLI-2 (`LC09_L2SP_147047_20211228_02_T1`, acquired 2021-12-28, 0.0% clouds)
- **Multi-Epoch 4-Panel Grid:** Click **"Multi-Epoch Comparison"** to expand a synchronized 4-panel view displaying all four historical epochs simultaneously around the target cell.
- **Historical Badge:** Transparently displays sensor, scene ID, acquisition date, and cloud cover.
- As prominently disclosed on the interface: **Present-day basemaps must NOT be used to judge historical land cover (1990/2000/2010).**

### E. Trajectory Assistant & Quality-Control (QC) Dashboard
- **Temporal Trajectory Card:** Displays the multi-epoch sequence (1990 -> 2000 -> 2010 -> 2020) for the active sample in real time. Flags potential reversion anomalies (e.g. built-up reverting to agriculture) for reviewer verification.
- **Quality-Control Dashboard:** Click **"QC Dashboard"** in the top bar to inspect live audit metrics:
  - Complete 4-epoch sample completion counts.
  - Per-epoch completion breakdowns.
  - Low confidence counts (Level 1 / Level 2).
  - Cloud / shadow / sensor issue flags.
  - `unavailable` class counts and trajectory anomalies.

### F. Usability & Keyboard Shortcuts
- **Ctrl+S / Cmd+S:** Instantly saves the active epoch annotation.
- **Unsaved Changes Guard:** Prompts a warning before navigating away if form fields have been modified without saving.
- **Keyboard Navigation:** Rapid epoch switching with clean field resets.

### G. Strict Protocol Validation
The form automatically enforces:
- Approved class vocabulary (`built_up`, `agriculture`, `natural_vegetation`, `water`, `bare_sparse`, `other`, `uncertain`, `ambiguous`, `unavailable`).
- Mandatory notes when `other` is chosen.
- Share bins (`>=75`, `50-75`, `<50`) and secondary class validation.
- Date window checks: imagery date must fall within $\pm 2$ calendar years of the target epoch.
- Confidence limit: `Landsat_context` cannot exceed confidence level 2.

### H. Segregated AI Assistance Placeholder
- Future AI suggestions appear in an isolated, purple-dashed panel labeled **"Experimental AI Suggestion Placeholder — Advisory Only"**.
- AI suggestions are never auto-filled or automatically saved into human ground-truth records.

---

## 3. Storage, Backups & Export

- **Working Storage:** Saved to atomic local JSON files in `labeling_app/storage/` (`t1_annotations.json` and `gold_annotations.json`).
- **Timestamped Backups:** Before any write, a timestamped snapshot is archived into `labeling_app/storage/backups/`.
- **Downstream CSV Export:** Clicking **"Export CSV"** produces an exact 35-column CSV matching `phase4_gold_key.csv` / `ingest_gold.py` specifications in `labeling_app/exports/`.

---

## 4. Running the Test Suite

Execute the automated test suite with:

```bash
python -m pytest tests/test_labeling_app.py -v
```
