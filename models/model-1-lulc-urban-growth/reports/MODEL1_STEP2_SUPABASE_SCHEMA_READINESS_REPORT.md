# GeoVerse Model 1: Step 2 — Supabase Schema Readiness & Validation Report

**Date:** October 29, 2026  
**Repository:** `GeoVerse27`  
**Target Module:** `models/model-1-lulc-urban-growth`  
**Application Entrypoint:** `http://127.0.0.1:5050` (`labeling_app/app.py`)  
**Auditor / Role:** Senior Supabase/PostgreSQL Architect & Backend Engineer  
**Scope:** Step 2 Only — Schema Preparation, Migration Validation, and Readiness Assessment  
**Operational Status:** `SCHEMA READY WITH DOCUMENTED BLOCKERS`

---

## 1. Executive Summary

This report delivers **Step 2** of the Supabase integration roadmap for **GeoVerse Model 1 (Historical LULC Classification & Spatio-Temporal Urban Growth Simulation)**. It completes a comprehensive validation of the PostgreSQL database schema migrations, verifies constraint alignment with the pre-registered scientific protocol, reviews Row Level Security (RLS) policies, and documents the safe deployment procedure.

In strict compliance with the Step 2 instructions:
1. **Zero Database Writes / Zero Schema Changes to Live DB:** No migrations were executed against a remote database.
2. **Zero Annotation Data Migration:** No annotation records were moved or transformed; the live application continues to use local JSON file storage (`GEOVERSE_STORAGE_BACKEND=json`).
3. **No Unrelated Code Changes:** Models 2 and 3 remain untouched, including all binary executables (`RouteOptimizer.exe`, `RouteOptimizer_Web.exe`).
4. **Preservation of Known Data Issue:** Sample `T2-0002` (epoch 2020) remains untouched with `dominant_class = 'ambiguous'` and empty `notes`. No synthetic notes or labels were fabricated.
5. **Preservation of Working Tree:** All manifests, JSON storage files, exports, backups, and reports remain intact.

---

## 2. Files Inspected & Modifications Made

### 2.1 Files Inspected
1. **Database Migrations (`models/model-1-lulc-urban-growth/db/migrations/`):**
   - `001_initial_schema.sql`: Core tables, constraints, indexes, triggers, and audit log.
   - `002_seed_datasets.sql`: Dataset registration for `t1` and `gold`.
   - `003_row_level_security.sql`: Row Level Security policies for `service_role`, `anon`, and `authenticated`.
2. **Configuration & Security:**
   - `.env.example`: Safe environment configuration template.
   - `.gitignore`: Exclusions for secrets, virtual environments, and local backups.
3. **Application Storage & Schema Validation Code (`labeling_app/`):**
   - `schema.py`: Protocol rules, classes, confidence bounds, date windows, and notes requirements.
   - `storage.py`: Dual-backend abstraction (`JsonAnnotationStore`, `SupabaseAnnotationStore`, `AnnotationStore`).
   - `app.py`: Flask REST API entry point with storage error-handling wrapper.
   - `migrate_annotations.py`: Safe migration CLI with inventory, validation, dry-run, and reconciliation.
4. **Data & Storage Files:**
   - `storage/t1_annotations.json`: Contains 3 active samples (`T2-0001`, `T2-0002`, `T2-0003`) across 6 epoch annotations.
   - `data/t1_manifest.json`: 699 spatial reference cells.
   - `data/gold_manifest.json`: 641 spatial reference cells (Tier-A evaluation holdout).
   - `data/double_interpretation_ids.json`: 140 T1 and 160 Gold double-interpretation IDs.
5. **Reports & Prior Audits:**
   - `reports/MODEL1_STEP1_SUPABASE_INFRASTRUCTURE_REPORT.md`
   - `reports/MODEL1_SUPABASE_ANNOTATION_MIGRATION_REPORT.md`

### 2.2 Modifications Made During Step 2
1. **`001_initial_schema.sql` Hardening:**
   - **Definite Class Constraint (`chk_definite_share_conf`):** Added `'other'` to the list of definite classes enforcing non-null `dominant_share_3bins` and `confidence_1to3`, aligning 100% with `DEFINITE_CLASSES` in `schema.py`.
   - **Completed Status Imagery Guard (`chk_status_done_imagery`):** Added `CONSTRAINT chk_status_done_imagery CHECK (status != 'done' OR (imagery_source IS NOT NULL AND imagery_date IS NOT NULL))` to guarantee that completed interpretations always include verified satellite imagery provenance.
   - **Automatic Timestamp Updates (`BEFORE UPDATE`):** Added dedicated `BEFORE UPDATE` trigger function `set_updated_at()` across `datasets`, `samples`, `annotations`, and `quality_reviews` so updates via SQL clients correctly maintain `updated_at`.
   - **Audit Trigger Permissions (`SECURITY DEFINER`):** Declared `record_annotation_history()` as `SECURITY DEFINER` with `SET search_path = public` to allow authenticated non-admin interpreters to update annotations without being blocked by RLS on `annotation_history`.
2. **`test_supabase_storage_and_migration.py` Expansion:**
   - Added explicit test assertions for `chk_status_done_imagery`, `SECURITY DEFINER`, and dataset seeding training flags (`t1` = True, `gold` = False).
   - Added focused tests verifying that `uncertain` does NOT require notes, while `other` mandates notes, area share bins, and confidence ratings.

---

## 3. Migration-by-Migration Review

### 3.1 Migration 1: `001_initial_schema.sql`
- **Tables Defined:**
  - `datasets`: Registry enforcing the research-integrity boundary between training and evaluation holdout.
  - `samples`: Stable 30 m cell reference points with composite unique constraint `(dataset_id, anon_id)`.
  - `annotations`: Epoch interpretations with dual unique constraints: `UNIQUE (dataset_id, anon_id, epoch)` and `UNIQUE (sample_id, epoch)`.
  - `annotation_history`: Immutable audit trail tracking every insert, update, delete, and migration action.
  - `quality_reviews`: Inter-rater agreement records, disagreement tracking, and arbitration metadata.
- **Relational Integrity & Foreign Keys:**
  - `samples.dataset_id REFERENCES datasets(dataset_id) ON DELETE RESTRICT`
  - `annotations.sample_id REFERENCES samples(id) ON DELETE RESTRICT`
  - `annotations.dataset_id REFERENCES datasets(dataset_id) ON DELETE RESTRICT`
  - `annotation_history.annotation_id REFERENCES annotations(id) ON DELETE SET NULL`
  - `quality_reviews.sample_id REFERENCES samples(id) ON DELETE CASCADE`
  - `quality_reviews.dataset_id REFERENCES datasets(dataset_id) ON DELETE RESTRICT`
- **Indexes:**
  - B-tree indexes on `(dataset_id, anon_id)`, `(lat, lon)`, `(dataset_id, anon_id, epoch)`, `(dominant_class, epoch)`, `(status)`, and `(created_at)`.
- **Idempotency:**
  - Employs `CREATE EXTENSION IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`, and `DROP TRIGGER IF EXISTS`, making the file safe for repeated execution without side effects.

### 3.2 Migration 2: `002_seed_datasets.sql`
- **Seed Data:**
  - `t1`: Name: *T1 Training and Tuning Dataset*, Total Samples: `699`, `is_training_allowed = TRUE`.
  - `gold`: Name: *Tier-A Gold Evaluation Benchmark Dataset*, Total Samples: `641`, `is_training_allowed = FALSE`.
- **Research Integrity Boundary:**
  - Explicitly hardcodes `is_training_allowed = FALSE` on the Gold dataset. Gold reference samples remain strictly protected from automated training ingestion.
- **Idempotency:**
  - Uses `ON CONFLICT (dataset_id) DO UPDATE SET ...`, allowing safe re-execution without duplicate key errors.

### 3.3 Migration 3: `003_row_level_security.sql`
- **RLS Activation:**
  - RLS is explicitly enabled on all 5 tables (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`).
- **Role Permissions & Least-Privilege Access:**
  - `service_role`: Full administrative access (`ALL`) for the Flask server backend and migration CLI. Service-role key is never exposed to browser clients.
  - `anon`: Granted read-only (`SELECT`) on `datasets` and `samples` to render client maps. Direct writes (`INSERT`/`UPDATE`/`DELETE`) are blocked.
  - `authenticated` (Annotators):
    - Granted `SELECT` on `datasets`, `samples`, `annotations`, `quality_reviews`.
    - Granted `INSERT` and `UPDATE` on `annotations` strictly where `dataset_id = 't1'`.
    - Direct write access to the `gold` evaluation benchmark is blocked at the database level.
    - Write access to `annotation_history` is handled securely via the `SECURITY DEFINER` trigger, ensuring users cannot forge audit records.
- **Idempotency:**
  - Uses `DROP POLICY IF EXISTS ... CREATE POLICY ...` on every policy declaration.

---

## 4. Schema & Validation Compatibility Findings

The SQL check constraints in `001_initial_schema.sql` were cross-referenced against `schema.py` and `INTERPRETER_PROTOCOL.md`:

| Protocol Rule | `schema.py` Rule | PostgreSQL Check Constraint | Status |
| :--- | :--- | :--- | :---: |
| **Allowed Epochs** | `EPOCHS = [2020, 2000, 2010, 1990]` | `CHECK (epoch IN (1990, 2000, 2010, 2020))` | **COMPATIBLE** |
| **Vocabulary** | 6 Definite + 3 Abstain classes | `dominant_class IN ('built_up', 'agriculture', 'natural_vegetation', 'water', 'bare_sparse', 'other', 'uncertain', 'ambiguous', 'unavailable')` | **COMPATIBLE** |
| **`unavailable` Status** | Stored as status, not land cover | `CHECK (status != 'unavailable' OR dominant_class IS NULL OR dominant_class = 'unavailable')` | **COMPATIBLE** |
| **`uncertain` Notes** | Notes are optional for `uncertain` | `CHECK (dominant_class NOT IN ('other', 'ambiguous') OR length(trim(notes)) > 0)` | **COMPATIBLE** |
| **`ambiguous` Notes** | Mandatory explanatory note | `CHECK (dominant_class NOT IN ('other', 'ambiguous') OR length(trim(notes)) > 0)` | **COMPATIBLE** |
| **`other` Notes** | Mandatory descriptive note | `CHECK (dominant_class NOT IN ('other', 'ambiguous') OR length(trim(notes)) > 0)` | **COMPATIBLE** |
| **Definite Share & Confidence** | Mandatory for all definite classes | `CHECK (dominant_class NOT IN ('built_up', 'agriculture', 'natural_vegetation', 'water', 'bare_sparse', 'other') OR (dominant_share_3bins IS NOT NULL AND confidence_1to3 IS NOT NULL))` | **COMPATIBLE** |
| **Landsat Confidence Cap** | Max confidence $\le 2$ on Landsat | `CHECK (imagery_source != 'Landsat_context' OR confidence_1to3 IS NULL OR confidence_1to3 <= 2)` | **COMPATIBLE** |
| **Secondary Class Rule** | Must differ from dominant class | `CHECK (second_class = 'none' OR second_class != dominant_class)` | **COMPATIBLE** |
| **Date Window Guard** | $\pm 2$ calendar years from epoch | `CHECK (imagery_date IS NULL OR (EXTRACT(YEAR FROM imagery_date) >= epoch - 2 AND EXTRACT(YEAR FROM imagery_date) <= epoch + 2))` | **COMPATIBLE** |
| **Downstream CSV Schema** | 35 wide columns (`ingest_gold.py`) | Maps cleanly to/from wide CSV export via `exporter.py` | **COMPATIBLE** |

---

## 5. Security & Row Level Security (RLS) Findings

1. **Least-Privilege Principle:**
   - Direct database access is restricted: browser clients connect exclusively to Flask REST API endpoints (`/api/...`).
   - The Flask server uses the `service_role` key server-side. The service-role key is never exposed to browser JavaScript or client-side assets.
2. **Audit Log Protection:**
   - End users and authenticated roles have no direct `INSERT`, `UPDATE`, or `DELETE` permissions on `annotation_history`.
   - The `record_annotation_history()` trigger function is declared `SECURITY DEFINER` with an explicit `SET search_path = public`, ensuring secure, unforgeable audit trail creation.
3. **Gold Dataset Segregation:**
   - RLS policy `auth_insert_t1_annotations` and `auth_update_t1_annotations` permit writes only where `dataset_id = 't1'`.
   - Modifying or inserting records into `gold` evaluation holdout requires service-role / administrative access.
4. **Credential Isolation:**
   - Real credentials are never stored in tracked files. `.gitignore` excludes `.env`, `*.env`, `*.key`, and `*.pem`.

---

## 6. Live Supabase Configuration & Connectivity Status

| Dimension | Verification Finding |
| :--- | :--- |
| **Environment Variables Configured** | **NO.** Neither `SUPABASE_URL` nor `SUPABASE_SERVICE_ROLE_KEY` is present in system environment variables or `.env`. |
| **Local `.env` File Present** | **NO.** No `.env` file exists in the repository. Only `.env.example` is tracked. |
| **Live Database Target** | **NONE.** No remote Supabase project has been assigned to this module. |
| **Live Database Reachability** | **UNREACHABLE.** Live connectivity cannot be tested without project credentials. |
| **Active Storage Engine** | **JSON FILE STORAGE.** `JsonAnnotationStore` remains the active production backend. |

---

## 7. Automated Test Results (Mocked vs Live)

All tests were executed using Python 3.14 on Windows:

```
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\Geoverse
collected 66 items

models/model-1-lulc-urban-growth/tests/test_labeling_app.py                      42 PASSED [ 63%]
models/model-1-lulc-urban-growth/tests/test_supabase_storage_and_migration.py   15 PASSED [ 86%]
models/model-2-property-valuation/tests/test_model2.py                            6 PASSED [ 95%]
models/model-3-smart-root-optimizer/tests/test_routing.py                         3 PASSED [100%]

============================= 66 passed in 1.73s ==============================
```

### Distinction of Test Execution Environments:
- **Mocked / Isolated Unit Tests (15 tests in `test_supabase_storage_and_migration.py`):**
  - Database operations were executed using `unittest.mock.MagicMock` mimicking the official `supabase-py` and `postgrest-py` SDK responses.
  - File-write and JSON tests used isolated temporary directories (`pytest` `tmp_path`).
- **Live Database Integration Tests:**
  - **Zero live database integration tests were executed** because no remote Supabase instance or credentials have been provisioned.

---

## 8. Preserved Known Data Issue: Sample `T2-0002` (Epoch 2020)

As documented in Step 1, inspection of `labeling_app/storage/t1_annotations.json` confirmed:
```json
"T2-0002": {
  "updated_at": "2026-10-21T08:15:49.741388+00:00",
  "epochs": {
    "2020": {
      "status": "done",
      "dominant_class": "ambiguous",
      "dominant_share_3bins": "50-75",
      "second_class": "agriculture",
      "confidence_1to3": 2,
      "imagery_source": "Landsat_context",
      "imagery_date": "2021-12-28",
      "notes": ""
    }
  }
}
```

### Protocol Analysis & Preservation:
- **Discrepancy:** `dominant_class = 'ambiguous'` requires an explanatory note under `INTERPRETER_PROTOCOL.md` and check constraint `chk_notes_mandatory`. The `notes` field is currently empty `""`.
- **Action Taken:** In strict adherence to scientific integrity rules, **this record was left completely unchanged**. No notes were fabricated, and the classification was not converted.
- **Handling Strategy:**
  - The migration CLI `--mode dry-run` accurately flags this record as a validation blocker.
  - When migration is authorized, `--skip-invalid` will isolate and quarantine `T2-0002:2020` for human visual interpreter resolution while permitting all valid records to migrate safely.

---

## 9. Safe Deployment Sequence for Approved Deployment

When live Supabase credentials are provided and deployment is explicitly authorized:

```
Step 1: Project Provisioning (DevOps)
   │
   ▼
Step 2: Schema Migration Execution (DBA via SQL Editor)
   │   ├── 001_initial_schema.sql
   │   ├── 002_seed_datasets.sql
   │   └── 003_row_level_security.sql
   ▼
Step 3: Verification SQL Queries (Post-Deployment Audit)
   │
   ▼
Step 4: Non-Destructive Dry-Run Connectivity Test (CLI)
   │
   ▼
Step 5: Hold Production Switch (Keep GEOVERSE_STORAGE_BACKEND=json)
```

### Exact SQL Deployment Order:
1. `001_initial_schema.sql` (Tables, constraints, indexes, triggers)
2. `002_seed_datasets.sql` (Seed `t1` and `gold`)
3. `003_row_level_security.sql` (Enable RLS, create policies)

---

## 10. Git Branch & Working-Tree Status

- **Branch:** `main` (commit `fceba97db29be57afc4e2fea2f73c51363da1596`)
- **Untracked Additions in Model 1:**
  - `db/migrations/001_initial_schema.sql` (refined)
  - `db/migrations/002_seed_datasets.sql`
  - `db/migrations/003_row_level_security.sql`
  - `.env.example`
  - `labeling_app/migrate_annotations.py`
  - `tests/test_supabase_storage_and_migration.py`
  - `reports/MODEL1_STEP1_SUPABASE_INFRASTRUCTURE_REPORT.md`
  - `reports/MODEL1_STEP2_SUPABASE_SCHEMA_READINESS_REPORT.md`
- **User Files & Models 2/3:** Fully preserved; no files in Model 2 or Model 3 were modified.

---

## 11. Outstanding Blockers

1. **Supabase Project Credentials Pending:** `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` must be provisioned by the project administrator.
2. **Interpreter Note Needed for `T2-0002` (2020):** Explanatory note required from the visual interpreter to clear the ambiguity validation check.
3. **Explicit Owner Sign-Off Required:** Migration execution against a live database requires explicit human authorization.

---

## 12. Final Step 2 Status

`SCHEMA READY WITH DOCUMENTED BLOCKERS`

> **Next Action:** Awaiting explicit review of this report and authorization before any remote database deployment or subsequent migration steps.
