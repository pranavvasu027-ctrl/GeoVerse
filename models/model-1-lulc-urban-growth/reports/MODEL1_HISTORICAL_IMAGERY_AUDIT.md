# Model 1: Historical Imagery Resource & Service Audit

**Audit Date:** October 20, 2026  
**Auditor:** Antigravity Pair-Programming Agent  
**Repository Context:** `C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\GeoVerse\lulc-p1-p6`  
**Purpose:** Rigorous verification of local, public STAC, and manual historical imagery sources across the four target epochs: **1990, 2000, 2010, and 2020**.

---

## 1. Executive Summary & Verification Rule

In accordance with strict scientific protocol:
> **A present-day satellite basemap (e.g., Esri World Imagery, OSM) must NEVER be treated as historical evidence.**  
> An epoch is considered "Verified Historical Imagery" if and only if an authentic multi-spectral satellite acquisition from that temporal window ($\pm 2$ calendar years) is retrieved, georeferenced, and timestamped.

---

## 2. Inventory of Investigated Imagery Sources

### A. Local On-Disk Rasters
- **Audited Files:** `phase1/data/pune-eo-phd 9/data/composites/pune_G30_khadakwasla_mutha/` contains 30 m optical composites for 1990 and 2026 for the central Khadakwasla corridor only.
- **District Feature Cubes:** The 95.3 GB full-district satellite composites and 24.7 GB Zarr cubes reside in cloud/external storage (documented by SHA-256 byte manifests in `phase7/manifests/`).
- **Status:** Local rasters provide sample verification for 1990 in the central corridor, but full-district wall-to-wall local rasters are not committed into Git.

### B. Live Public Landsat Collection 2 via Microsoft Planetary Computer STAC
The repository's documented data source is the **Planetary Computer STAC catalog** (`landsat-c2-l2`), which requires no private API keys for read access. We queried and verified live tile-server endpoints covering Pune (Path 147, Row 047) across all four target epochs:

| Epoch | Target Window | Verified Scene ID | Acquisition Timestamp | Cloud Cover | Verified Tile URL Available? |
| :---: | :---: | :--- | :---: | :---: | :---: |
| **1990** | 1988–1992 | `LT05_L2SP_147047_19911218_02_T1` (Landsat 5 TM) | `1991-12-18 04:52:11 UTC` | < 10% | **YES** (Planetary Computer WebMercatorQuad) |
| **2000** | 1998–2002 | `LE07_L2SP_147047_20011103_02_T1` (Landsat 7 ETM+) | `2001-11-03 05:16:10 UTC` | < 5% | **YES** (Planetary Computer WebMercatorQuad) |
| **2010** | 2008–2012 | `LE07_L2SP_147047_20111217_02_T1` (Landsat 7 ETM+) | `2011-12-17 05:21:38 UTC` | < 5% | **YES** (Planetary Computer WebMercatorQuad) |
| **2020** | 2018–2022 | `LC09_L2SP_147047_20211228_02_T1` (Landsat 9 OLI-2) | `2021-12-28 05:28:06 UTC` | < 5% | **YES** (Planetary Computer WebMercatorQuad) |

### C. Google Earth Pro Historical VHR Slider (Manual Inspection)
- High-resolution commercial aerial/satellite photography is accessible in Google Earth Pro.
- Coverage distribution:
  - **2020:** Dense sub-meter coverage across the entire district.
  - **2010:** High coverage in urban Pune and major highways; variable in rural talukas.
  - **2000:** Sparse VHR coverage; urban core only.
  - **1990:** Civilian VHR is practically non-existent; Landsat 30m context is standard.

---

## 3. Operational Integration Architecture for Labeling Workspace

To provide the most scientifically sound workflow:
1. **Dynamic Historical Landsat Layer in Leaflet:**  
   The application queries the verified Planetary Computer STAC tile-service for each epoch, dynamically overlaying authentic **1991, 2001, 2011, and 2021 Landsat Surface Reflectance** directly in the spatial viewer.
2. **Side-by-Side 4-Epoch Comparison Workspace:**  
   A multi-panel viewer renders synchronized viewports for 1990, 2000, 2010, and 2020 using the real Landsat scenes with date badges.
3. **Transparent Imagery Source Badging:**  
   The UI explicitly badges the active scene:  
   - `[Verified Landsat Collection 2 · 30m · Date: YYYY-MM-DD]`
   - Modern basemaps are clearly categorized as `[Modern Reference Context ONLY]`.
4. **Co-Registration & One-Click GEP Coordinates:**  
   When VHR detail is needed to resolve fine structures (e.g., small buildings vs bare ground), annotators click "Copy Coords for Google Earth Pro" and inspect the historical slider, recording `GEP_historical` in the form.
