# GeoVerse Model 1: Dataset Readiness Report

**Report Date:** October 21, 2026  
**Scope:** Model 1 (Historical LULC Classification & Urban Growth)  
**Target Repository:** `C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\GeoVerse\lulc-p1-p6`  

---

## 1. Executive Summary

This report presents a complete empirical inventory of the two core reference datasets for GeoVerse Model 1:
1. **Tier-A Gold Evaluation Dataset (641 samples)**
2. **T1 Training & Tuning Dataset (699 samples)**

Both datasets have been verified for spatial integrity, sample uniqueness, target cell geometry, and downstream schema compatibility.

---

## 2. Dataset Inventory & Statistical Profile

| Metric | Tier-A Gold Evaluation Dataset | T1 Training & Tuning Dataset | Combined Reference Universe |
|---|---|---|---|
| **Total Sample Records** | 641 | 699 | 1,340 |
| **Unique Sample IDs** | 641 (`P4-0001` .. `P4-0641`) | 699 (`T2-0001` .. `T2-0699`) | 1,340 |
| **Duplicate IDs** | **0** | **0** | **0** |
| **Missing Coordinates** | **0** | **0** | **0** |
| **Invalid Coordinates (outside region)** | **0** | **0** | **0** |
| **Missing Polygon Geometry** | **0** | **0** | **0** |
| **Invalid Geometry (unclosed ring)** | **0** | **0** | **0** |
| **Target Cell Resolution** | $30\text{ m} \times 30\text{ m}$ (mean span $30.3\text{ m}$) | $30\text{ m} \times 30\text{ m}$ (mean span $30.3\text{ m}$) | $30\text{ m} \times 30\text{ m}$ |
| **Stratification / Partitions** | 13 strata, 125 spatial blocks | 525 `train` / 174 `tuning` | Strictly disjoint |
| **Double-Interpretation Subset** | 160 points (Interpreter B) | 140 points (Interpreter B) | 300 dual-adjudication points |
| **Completed Human Annotations** | **0 / 641 (0.0%)** | **0 / 699 (0.0%)** | **0 / 1,340 (0.0%)** |
| **In-Progress Annotations** | 0 | 0 | 0 |
| **Unlabeled Samples** | 641 (100.0%) | 699 (100.0%) | 1,340 (100.0%) |
| **Genuine Reference Labels Found** | **None** | **None** | **None** |

---

## 3. Spatial & Historical Imagery Coverage

### 3.1 Primary Landsat Footprint vs. Perimeter Samples
All samples were evaluated against the 4-epoch intersection footprint of Landsat Path 147, Row 047:

- **Gold Dataset (641 samples):**
  - Inside Path 147, Row 047 Footprint: **624 samples (97.3%)**
  - Perimeter Samples (outside 147_047): **17 samples (2.7%)**
- **T1 Dataset (699 samples):**
  - Inside Path 147, Row 047 Footprint: **662 samples (94.7%)**
  - Perimeter Samples (outside 147_047): **37 samples (5.3%)**

### 3.2 Perimeter Handling Strategy
Perimeter points (located primarily in eastern Indapur taluka or far western Ghats) cannot be fully resolved by a single Path 147 / Row 047 scene. Annotators inspecting these points must use the **Google Earth Pro historical slider** (`imagery_source: GEP_historical`) or adjacent Landsat path/rows.

---

## 4. Feature File & Raster Inventory

A rigorous audit was conducted on all local feature storage paths:

| Feature Asset | Documented Path | Local Disk Status | Readiness Decision |
|---|---|---|---|
| **Full-District Feature Cube** | `data/features/cube/pune_G30.zarr` | **ABSENT** (Exists: False) | **NOT READY** (Requires external cloud rebuild or processing) |
| **Landsat Harmonized C2TM Cube** | `data/features/cube/pune_G30_landsat_c2tm.zarr` | **ABSENT** | **NOT READY** |
| **Pilot Cube QA Layers (1990/2000)** | `phase5/data/phase5_pilot_cube_QA_layers_1990_2000.zip` | PRESENT (8 GeoTIFFs) | Available for diagnostic checks only |
| **Pilot Cube QA Layers (2010/2020)** | `phase5/data/phase5_pilot_cube_QA_layers_2010_2020.zip` | PRESENT (8 GeoTIFFs) | Available for diagnostic checks only |
| **District Silver Baseline Mask** | `results/phase7/manifests/silver/manifest_v1.json` | PRESENT (SHA verified) | Available as baseline comparative mask |
| **Terrain Covariates (SRTM/ALOS)** | `data/features/terrain/` | **ABSENT** (OOM killed during pilot) | Needs compute run |

---

## 5. Dataset Readiness Verdict

- **Sample Geometries and Manifests:** **100% READY** (Fully validated, indexed, and loaded in labeling app).
- **Labeling Infrastructure:** **100% READY** (Protocol enforced, atomic persistence active, STAC tiles accessible).
- **Reference Labels:** **0.0% READY** (Awaiting human visual interpretation).
- **District Feature Rasters:** **0.0% READY** (Zarr feature cube not built on local disk).

**Conclusion:** The datasets are structurally sound and ready for human reference interpretation, but model training is blocked until labels are generated.

---

## 2026-10-21 completion-audit addendum

Fresh storage inspection found one partial T1 2020 record and zero Gold records. Because the app storage schema records neither an interpreter nor independent-review provenance, this record is not evidence of a genuine protocol-compliant reference label and is excluded from training/evaluation readiness. Current queues are T1 698 unannotated / 1 partial / 0 complete and Gold 641 / 0 / 0. No local `.zarr` feature cube was found. The configured Landsat scene metadata was not live-reverified because DNS resolution to Planetary Computer failed; the primary-scene counts remain queue heuristics, not coverage proof. Dataset readiness is therefore **PARTIALLY READY, NOT TRAINING READY**.
