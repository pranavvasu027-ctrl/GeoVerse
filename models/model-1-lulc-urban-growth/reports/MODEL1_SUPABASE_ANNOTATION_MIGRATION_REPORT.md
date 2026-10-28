# GeoVerse Model 1: Supabase Annotation Database Integration & Safe JSON Migration Report

**Date:** October 29, 2026  
**Target Module:** `models/model-1-lulc-urban-growth`  
**Application Endpoint:** `http://127.0.0.1:5050`  
**Repository Branch:** `main`  
**Author / Auditor:** Senior Backend Engineer, GIS Data Engineer & PostgreSQL/Supabase Architect  
**Migration Status:** `TESTED — NOT MIGRATED`

---

## 1. Executive Summary

This engineering report establishes the architectural assessment, relational schema design, dual-backend storage abstraction, repeatable migration tooling, and validation framework for migrating reference annotations in **GeoVerse Model 1 (Historical LULC Classification & Spatio-Temporal Urban Growth Simulation)** from local JSON files to a PostgreSQL database hosted on **Supabase**.

In strict accordance with the mandatory safety directives:
1. **Zero Data Loss / Zero Fabrication:** No reference labels were fabricated, altered, or overwritten. Existing JSON files and backups remain 100% intact.
2. **Fail-Closed Safeguards:** Live model training remains blocked (`NOT TRAINING READY`) until all scientific protocol requirements are satisfied.
3. **No Silent Fallback:** The storage layer avoids silent fallback from database to JSON during database write failures, preventing divergent split-brain state.
4. **Current Operational Status:** Because live Supabase project credentials (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) are not yet provisioned in the environment, the live labeling application is deliberately retained in **JSON mode** (`GEOVERSE_STORAGE_BACKEND=json`). The database integration is **TESTED — NOT MIGRATED**.

---

## 2. Existing Architecture & Verified Supabase Status

### 2.1 Pre-Migration Architecture
- **Web Application:** Flask application (`labeling_app/app.py`), listening strictly on loopback `127.0.0.1:5050`.
- **Active Storage Engine:** `JsonAnnotationStore` in `labeling_app/storage.py`.
- **Primary Annotation File:** `labeling_app/storage/t1_annotations.json` (contains 3 sample IDs: `T2-0001`, `T2-0002`, `T2-0003`, with 6 epoch annotation records).
- **Evaluation Holdout File:** `labeling_app/storage/gold_annotations.json` (currently non-existent on disk; 0 Gold annotations completed).
- **Sample Manifests:**
  - `data/t1_manifest.json`: 699 spatial sample cells (30 m resolution across Pune District).
  - `data/gold_manifest.json`: 641 spatial sample cells (Tier-A Gold evaluation holdout).
  - Total: 1,340 spatial reference samples across four historical epochs (1990, 2000, 2010, 2020).
- **Dual Interpretation Registry:** `data/double_interpretation_ids.json` (140 T1 sample IDs, 160 Gold sample IDs designated for independent peer review).
- **Work Queue & QC:** Persistent queue management (`storage/work_queue_t1.json`, `storage/work_queue_gold.json`) and real-time QC analytics (`qc.py`).
- **Downstream Export:** `exporter.py` generating the authoritative 35-column CSV schema (`ingest_gold.py` format).

### 2.2 Verified Supabase Status
- **Inspection Findings:** An exhaustive repository and environment audit confirmed that **Supabase was not previously configured or connected to GeoVerse Model 1**.
  - No database migration files or SQL schemas existed in the repository.
  - No `.env` or configuration files containing Supabase references were present.
  - System environment variables for `SUPABASE_URL`, `SUPABASE_KEY`, or `DATABASE_URL` were empty.
  - Python packages `supabase` (v2.32.0) and `postgrest` (v2.32.0) are installed in the Python 3.14 environment, but lacked configuration credentials.
- **Decision:** Model 1 must NOT be switched to Supabase in production until live credentials, database schemas, Row Level Security, and migration dry-runs are validated and explicitly authorized by the project leads.

---

## 3. Database Schema Design & SQL Migrations

A production-grade, 3NF-normalized relational schema was architected to mirror the pre-registered scientific protocol (`INTERPRETER_PROTOCOL.md`) while enforcing database-level constraints.

All migrations are maintained under `models/model-1-lulc-urban-growth/db/migrations/`:

### 3.1 `001_initial_schema.sql` (Core Relational Tables & Constraints)

```
┌─────────────────────────────────┐
│            datasets             │
├─────────────────────────────────┤
│ PK  dataset_id (VARCHAR(32))    │
│     name (VARCHAR(128))         │
│     description (TEXT)          │
│     is_training_allowed (BOOL)  │◄── Enforces training vs gold holdout boundary
│     total_samples (INT)         │
│     created_at / updated_at     │
└───────────────┬─────────────────┘
                │ 1
                │
                │ N
┌───────────────▼─────────────────┐
│             samples             │
├─────────────────────────────────┤
│ PK  id (BIGSERIAL)              │
│ FK  dataset_id ──► datasets     │
│     anon_id (VARCHAR(64))       │
│     lat / lon (DOUBLE PRECISION)│
│     polygon (JSONB)             │
│     inside_primary_landsat (BOOL│
│     is_double_interpretation(BL)│
│ UQ  (dataset_id, anon_id)       │
└───────────────┬─────────────────┘
                │ 1
                │
                │ N
┌───────────────▼─────────────────┐       ┌─────────────────────────────────┐
│           annotations           │       │       annotation_history        │
├─────────────────────────────────┤       ├─────────────────────────────────┤
│ PK  id (BIGSERIAL)              │       │ PK  history_id (BIGSERIAL)      │
│ FK  sample_id ──► samples       │       │ FK  annotation_id ──► annotat.  │
│ FK  dataset_id ──► datasets     │       │     dataset_id / anon_id / epoch│
│     anon_id (VARCHAR(64))       │       │     action (INSERT/UPDATE/DEL)  │
│     epoch (1990/2000/2010/2020) │       │     old_values / new_values     │
│     status (done/unavail/skip)  │       │     changed_by / changed_at     │
│     dominant_class (VARCHAR(32))│       └─────────────────────────────────┘
│     dominant_share_3bins        │                        ▲
│     second_class                │                        │ Trigger:
│     confidence_1to3 (1, 2, 3)   │                        │ trg_record_annotation_
│     imagery_source              │                        │ history
│     imagery_date (DATE)         │                        │
│     notes (TEXT)                │────────────────────────┘
│     annotator_id (VARCHAR(64))  │
│ UQ  (dataset_id, anon_id, epoch)│       ┌─────────────────────────────────┐
│ UQ  (sample_id, epoch)          │       │         quality_reviews         │
└─────────────────────────────────┘       ├─────────────────────────────────┤
                                          │ PK  review_id (BIGSERIAL)       │
                                          │ FK  sample_id ──► samples       │
                                          │     interpreter_a / class / conf│
                                          │     interpreter_b / class / conf│
                                          │     is_agreement (BOOL)         │
                                          │     adjudicated_class           │
                                          │     review_status               │
                                          │ UQ  (dataset_id, anon_id, epoch)│
                                          └─────────────────────────────────┘
```

#### Enforced Server-Side Constraints:
1. **Epoch Integrity:** `CHECK (epoch IN (1990, 2000, 2010, 2020))`
2. **Status vs Dominant Class:** `CHECK (status != 'done' OR dominant_class IS NOT NULL)`
3. **Unavailable Status Consistency:** `status = 'unavailable'` is stored as a record status rather than a land cover category: `CHECK (status != 'unavailable' OR dominant_class IS NULL OR dominant_class = 'unavailable')`
4. **Mandatory Notes on Ambiguity/Other:** `CHECK (dominant_class NOT IN ('other', 'ambiguous') OR length(trim(notes)) > 0)`
5. **Definite Class Requirements:** Definite classes (`built_up`, `agriculture`, `natural_vegetation`, `water`, `bare_sparse`) mandate both `dominant_share_3bins` and `confidence_1to3`.
6. **Landsat Context Cap:** When `imagery_source = 'Landsat_context'`, `confidence_1to3` cannot exceed `2`.
7. **Second Class Rule:** `second_class` cannot equal `dominant_class` unless `none`.
8. **Date Window Guard:** `imagery_date` year must fall strictly within `[epoch - 2, epoch + 2]`.
9. **Automatic History Trigger:** PostgreSQL trigger `trg_record_annotation_history` automatically logs all row mutations to `annotation_history`.

### 3.2 `002_seed_datasets.sql` (Dataset Boundaries)
- **T1 Dataset:** `dataset_id='t1'`, `total_samples=699`, `is_training_allowed=TRUE`.
- **Gold Dataset:** `dataset_id='gold'`, `total_samples=641`, `is_training_allowed=FALSE` (strictly reserved for independent model evaluation).

### 3.3 `003_row_level_security.sql` (Access Control & Role Boundaries)
- **RLS Enabled:** Activated across all 5 tables.
- **Service Role:** Full privileges (`ALL`) for server-side Flask application and migration CLI.
- **Anonymous Role (`anon`):** Read-only access to `datasets` and `samples` to render client maps. Direct writes (`INSERT`/`UPDATE`/`DELETE`) are completely blocked.
- **Authenticated Role (`authenticated`):** Read access to reference data and annotations. Write privileges restricted strictly to `dataset_id = 't1'`. Modifying `gold` evaluation holdout requires service-role/admin privileges.

---

## 4. Storage Abstraction Architecture

The application persistence layer in `labeling_app/storage.py` was refactored into a unified, extensible abstraction:

```python
BaseAnnotationStore (ABC)
   ├── JsonAnnotationStore       # Local atomic JSON writes + timestamped backups
   └── SupabaseAnnotationStore   # PostgreSQL/Supabase database client + upsert transactions

AnnotationStore (Polymorphic Factory)
   └── Instantiates JsonAnnotationStore or SupabaseAnnotationStore based on GEOVERSE_STORAGE_BACKEND
```

### Key Technical Properties:
1. **100% Backward Compatibility:** Calling `AnnotationStore(storage_dir)` or `AnnotationStore()` defaults cleanly to `JsonAnnotationStore`. All existing tests, paths, and methods (`load_annotations`, `save_sample_annotation`, `get_sample_annotation`) remain identical.
2. **Seamless Dict Mapping:** `SupabaseAnnotationStore.load_annotations()` maps relational database rows into the exact nested JSON dictionary structure:
   ```json
   {
     "anon_id": {
       "updated_at": "2026-10-28T12:00:00+00:00",
       "epochs": {
         "2020": {
           "status": "done",
           "dominant_class": "water",
           "dominant_share_3bins": ">=75",
           "second_class": "none",
           "confidence_1to3": 3,
           "imagery_source": "GEP_historical",
           "imagery_date": "2020-04-10",
           "notes": ""
         }
       }
     }
   }
   ```
3. **No Split-Brain Failures:** If a database write encounters a network timeout, constraint violation, or disconnect, `SupabaseAnnotationStore` raises `StorageWriteError`. It deliberately **does NOT fall back to writing to JSON**, ensuring records never diverge between two active sources of truth.
4. **App Error Handling:** `labeling_app/app.py` catches `StorageError` and returns clean HTTP 500 error payloads (`{"status": "storage_error", "error": "..."}`) without crashing the application process.

---

## 5. Safe Migration & Reconciliation Engine

The migration script `labeling_app/migrate_annotations.py` provides an auditable, repeatable migration utility with dry-run and reconciliation safeguards.

### 5.1 Command Capabilities:
```bash
# 1. Inventory manifests, annotations, and backup archives
python -m labeling_app.migrate_annotations --mode inventory

# 2. Validate all source records against schema rules
python -m labeling_app.migrate_annotations --mode validate

# 3. Dry-run migration plan generation (zero writes, no credentials needed)
python -m labeling_app.migrate_annotations --mode dry-run

# 4. Dry-run with invalid record quarantine
python -m labeling_app.migrate_annotations --mode dry-run --skip-invalid

# 5. Production migration (strictly requires --confirm flag and live connection)
python -m labeling_app.migrate_annotations --mode migrate --confirm

# 6. Post-migration field-by-field reconciliation
python -m labeling_app.migrate_annotations --mode reconcile
```

### 5.2 Real Source Inventory Results:
Running `--mode inventory` against the live repository produced the following verified inventory:
- **Manifest Samples:**
  - `t1_manifest.json`: 699 samples (0 duplicates, SHA-256: `b7226aa4...`)
  - `gold_manifest.json`: 641 samples (0 duplicates, SHA-256: `df23ca84...`)
  - Total Manifest Samples: 1,340
- **Existing Annotations:**
  - `t1_annotations.json`: 3 samples (`T2-0001`, `T2-0002`, `T2-0003`), 6 epoch annotations (SHA-256: `4fbbcc88...`)
  - `gold_annotations.json`: 0 samples, 0 annotations (honest zero count)
- **Backups:** 6 timestamped backup files preserved in `labeling_app/storage/backups/`.

### 5.3 Schema Validation Audit Findings:
Running `--mode validate` detected 1 authentic schema violation in existing JSON storage:
- **Record:** `T2-0002`, Epoch `2020`.
- **Issue:** `dominant_class = "ambiguous"`, but `notes = ""` (empty string).
- **Rule:** Under `INTERPRETER_PROTOCOL.md`, transitional ambiguity requires explanatory notes.
- **Safety Handling:** In strict compliance with Safety Rule 8, **no fake notes were fabricated**. The migration engine isolates this record:
  - Default dry-run flags the record as a **migration blocker**.
  - Using `--skip-invalid` flags and quarantines `T2-0002:2020` for human interpreter review while permitting the 5 valid records (`T2-0001` epochs 1990, 2000, 2010, 2020 and `T2-0003` epoch 2020) to be migrated cleanly.

---

## 6. Files Changed & Added

| File Path | Type | Description |
| :--- | :---: | :--- |
| `models/model-1-lulc-urban-growth/db/migrations/001_initial_schema.sql` | Added | Master PostgreSQL DDL: 5 tables, constraints, indexes, audit trigger. |
| `models/model-1-lulc-urban-growth/db/migrations/002_seed_datasets.sql` | Added | Seeds `t1` and `gold` datasets with training authorization flags. |
| `models/model-1-lulc-urban-growth/db/migrations/003_row_level_security.sql` | Added | RLS policies for `service_role`, `anon`, and `authenticated`. |
| `models/model-1-lulc-urban-growth/.env.example` | Added | Safe environment variable template with security guidelines. |
| `models/model-1-lulc-urban-growth/labeling_app/storage.py` | Modified | Dual-backend storage abstraction (`BaseAnnotationStore`, `JsonAnnotationStore`, `SupabaseAnnotationStore`, `AnnotationStore`). |
| `models/model-1-lulc-urban-growth/labeling_app/app.py` | Modified | Wrapped storage persistence in try/except to handle `StorageError` without silent JSON fallback. |
| `models/model-1-lulc-urban-growth/labeling_app/migrate_annotations.py` | Added | Safe migration CLI with inventory, validation, dry-run, idempotent migration, and reconciliation. |
| `models/model-1-lulc-urban-growth/tests/test_supabase_storage_and_migration.py` | Added | 15 comprehensive unit, schema, mock-database, rollback, and reconciliation tests. |
| `models/model-1-lulc-urban-growth/reports/MODEL1_SUPABASE_ANNOTATION_MIGRATION_REPORT.md` | Added | This authoritative engineering report. |

---

## 7. Automated Test Results

All tests were executed across the test suite on Python 3.14 (Windows 64-bit):

### 7.1 Unit & Integration Test Summary

```
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\prana\OneDrive\Desktop\3rd SEM\Group Projects\EDI\Geoverse
collected 66 items

models/model-1-lulc-urban-growth/tests/test_labeling_app.py                      42 PASSED [ 63%]
models/model-1-lulc-urban-growth/tests/test_supabase_storage_and_migration.py   15 PASSED [ 86%]
models/model-2-property-valuation/tests/test_model2.py                            6 PASSED [ 95%]
models/model-3-smart-root-optimizer/tests/test_routing.py                         3 PASSED [100%]

============================= 66 passed in 2.50s ==============================
```

### 7.2 Breakdown of Supabase & Migration Tests (15 Tests)

| Test Identifier | Category | Result | Description |
| :--- | :---: | :---: | :--- |
| `test_supabase_storage_missing_credentials_raises_config_error` | Security | **PASS** | Missing URL/keys raises `StorageConfigurationError`. |
| `test_supabase_storage_ping_success_and_failure` | Connection | **PASS** | Validates healthy ping vs timeout/network failure handling. |
| `test_storage_polymorphic_factory` | Architecture | **PASS** | Verifies dynamic backend switching (`json` vs `supabase`). |
| `test_sql_migration_files_exist_and_contain_constraints` | Schema | **PASS** | Validates all table DDL, check constraints, triggers, and RLS. |
| `test_schema_vocabulary_and_constraint_validation` | Validation | **PASS** | Tests class rejection, note rules, Landsat cap, date window. |
| `test_supabase_storage_save_reload_and_isolation` | Persistence | **PASS** (Mocked) | Verifies Supabase upsert payload structure and dict reload. |
| `test_supabase_write_failure_raises_and_never_falls_back_to_json` | Integrity | **PASS** | Write error raises `StorageWriteError`; JSON remains untouched. |
| `test_migration_inventory_and_validation` | Migration | **PASS** | Validates inventory counting and detects schema errors. |
| `test_migration_dry_run_produces_plan_without_writes` | Migration | **PASS** | Dry-run computes plan without writing or modifying files. |
| `test_migration_confirmation_guard_prevents_accidental_writes` | Safety | **PASS** | Fails closed if `--confirm` flag is omitted. |
| `test_migration_execution_and_idempotency_mocked` | Migration | **PASS** (Mocked) | Repeated migration runs are idempotent with 0 duplicates. |
| `test_field_by_field_reconciliation` | Reconciliation | **PASS** | Compares 8 fields per record and flags subtle discrepancies. |
| `test_work_queue_and_qc_compatibility` | Compatibility | **PASS** | Work queue and QC stats work seamlessly with store. |
| `test_csv_export_schema_compatibility_from_store` | Downstream | **PASS** | Generates exact 35-column CSV matching `ingest_gold.py`. |
| `test_training_readiness_fail_closed_guard` | Scientific Guard | **PASS** | Preflight training gate fails closed (`BLOCKED`). |

---

## 8. Rollback & Disaster Recovery Procedures

Because the original JSON files are preserved read-only and backed up automatically on every write, rollbacks are deterministic:

### 8.1 Rollback from Supabase to JSON Backend
If a deployed Supabase instance experiences latency, rate limiting, or connection issues, the live application can be restored to local JSON storage immediately without service interruption:
1. Update environment variable in `.env`:
   ```bash
   GEOVERSE_STORAGE_BACKEND=json
   ```
2. Restart the application:
   ```bash
   cd models/model-1-lulc-urban-growth
   python -m labeling_app.app
   ```
3. Verify that `/api/manifest` and `/api/annotation/t1/T2-0001` return the locally persisted records.

### 8.2 JSON Storage Archive Recovery
If JSON storage requires restoration to a prior point in time:
- Timestamped backups are preserved in `labeling_app/storage/backups/`.
- Copy the desired backup timestamp over `t1_annotations.json`:
  ```bash
  cp labeling_app/storage/backups/t1_annotations_<timestamp>.json labeling_app/storage/t1_annotations.json
  ```

---

## 9. Remaining Blockers & Migration Prerequisite Checklist

Before switching production storage to Supabase (`GEOVERSE_STORAGE_BACKEND=supabase`), the following administrative actions are required:

| Prerequisite | Responsible Party | Status | Action Required |
| :--- | :---: | :---: | :--- |
| **1. Supabase Project Provisioning** | DevOps / Team Lead | **PENDING** | Create Supabase project in desired region (e.g., AWS Mumbai / `ap-south-1`). |
| **2. SQL Schema Deployment** | Database Admin | **READY** | Execute `001_initial_schema.sql`, `002_seed_datasets.sql`, `003_row_level_security.sql` via Supabase SQL Editor. |
| **3. Credential Provisioning** | DevOps | **PENDING** | Populate `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in server-side `.env`. |
| **4. T2-0002 Ambiguity Note** | Human Interpreter | **PENDING** | Provide explanatory note for sample `T2-0002` (2020) to satisfy protocol rules. |
| **5. Migration Execution** | Backend Engineer | **READY** | Run `python -m labeling_app.migrate_annotations --mode migrate --confirm`. |
| **6. Post-Migration Reconciliation** | QA Engineer | **READY** | Run `python -m labeling_app.migrate_annotations --mode reconcile` (verify 100% match). |
| **7. Production Backend Switch** | System Architect | **HOLD** | Change `GEOVERSE_STORAGE_BACKEND=supabase` in `.env` and restart app. |

---

## 10. Handover & Developer Guide

### Where Are New Annotations Actually Saved Right Now?
- **Active Backend:** Local JSON storage (`JsonAnnotationStore`).
- **File Location:** `models/model-1-lulc-urban-growth/labeling_app/storage/t1_annotations.json`.
- **Automatic Backups:** Every successful write creates an immutable timestamped backup in `models/model-1-lulc-urban-growth/labeling_app/storage/backups/t1_annotations_<nanoseconds>.json`.

### How to Verify a Saved Record
1. Query the live API endpoint:
   ```bash
   curl http://127.0.0.1:5050/api/annotation/t1/T2-0001
   ```
2. Or inspect the JSON file directly:
   ```bash
   python -c "import json; print(json.load(open('labeling_app/storage/t1_annotations.json'))['T2-0001'])"
   ```

### Is the Live Application Using JSON or Supabase?
- **Current Operational Mode:** **Local JSON Storage**.
- The application will remain in JSON storage mode until live credentials are provided and the migration is explicitly executed with `--confirm`.
