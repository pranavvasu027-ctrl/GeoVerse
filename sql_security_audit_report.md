# GeoVerse27 — Final Supabase SQL Security & Pre-Deployment Audit Report

**Date:** October 29, 2026  
**Auditor:** Integration HQ (AG)  
**Target Project:** `bciurjfbrplvruacldsx` (Project: `GeoVerse`, Org: `Bahubali`, Region: `ap-northeast-1` Tokyo)  
**Target Engine:** PostgreSQL 17.11.0.003  
**Overall Readiness Conclusion:** **READY FOR HUMAN APPROVAL**  

---

## 1. Executive Summary

A comprehensive, line-by-line security and integrity audit of all three migration files (`001_initial_schema.sql`, `002_seed_datasets.sql`, `003_row_level_security.sql`) and associated Model 1 application code (`storage.py`, `app.py`, `readiness.py`, `migrate_annotations.py`) has been completed. 

Two defense-in-depth security improvements were identified, implemented, and validated:
1. **Schema-Level Gold Holdout Invariant:** Added `CONSTRAINT chk_gold_never_training CHECK (dataset_id != 'gold' OR is_training_allowed = FALSE)` to `datasets` table in `001_initial_schema.sql`.
2. **Object-Level Privilege Hardening:** Added explicit `REVOKE`/`GRANT` statements for tables, sequences, and `SECURITY DEFINER` functions in `003_row_level_security.sql`, ensuring that permissions cannot be escalated even if RLS were bypassed.

Both `npx supabase db push --dry-run` and `npx supabase db lint --linked` executed cleanly with **0 errors**. The full test suite of **101 tests passed (100% green)**.

---

## 2. Security Controls & Audit Findings Table

| Security / Control | Exact File & SQL Location | Finding | Severity | Evidence / Test Performed | Correction Made | Remaining Risk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **RLS Activation** | `003_row_level_security.sql` (L8–12) | RLS enabled on all 5 application tables (`datasets`, `samples`, `annotations`, `annotation_history`, `quality_reviews`). | Low (Positive) | Static SQL verification & `db lint --linked` | None needed; verified active. | None. Unauthenticated queries denied by default. |
| **Anonymous (`anon`) Isolation** | `003_row_level_security.sql` (L46–52, L115–128) | `anon` is granted `SELECT` only on `datasets` and `samples`. Zero write or history policies exist for `anon`. | Medium | Verified with `REVOKE ALL ON TABLE annotations, quality_reviews, annotation_history FROM anon` | Added explicit `REVOKE ALL` table grants to block raw table access. | None. Public browsers cannot read or write annotations. |
| **Authenticated Annotator Scope** | `003_row_level_security.sql` (L76–85, L122–126) | Authenticated users can insert/update only `t1` annotations (`WITH CHECK (dataset_id = 't1')`). No `DELETE` policy exists for `authenticated`. | Low (Positive) | Static SQL analysis + `test_sql_migration_files_exist_and_contain_constraints` | Added `REVOKE DELETE, TRUNCATE ON TABLE annotations FROM authenticated`. | Minimal. Backend API verifies payload before submission. |
| **Gold Holdout Isolation (Write Guard)** | `003_row_level_security.sql` (L76–85) | `auth_insert_t1_annotations` and `auth_update_t1_annotations` strictly enforce `dataset_id = 't1'` in both `USING` and `WITH CHECK`. | Critical (Positive) | RLS analysis: Attempting to insert or update `dataset_id = 'gold'` is rejected by PostgreSQL. | Added table-level `CONSTRAINT chk_gold_never_training` to `datasets` in `001_initial_schema.sql`. | None. Impossible to mark Gold as training data or write Gold annotations as an ordinary user. |
| **Gold Training Flag Inviolability** | `001_initial_schema.sql` (L13–22) | Database schema lacked an engine-level invariant prohibiting `is_training_allowed = TRUE` for `gold`. | Medium | Schema inspection in `001_initial_schema.sql` | Added `CONSTRAINT chk_gold_never_training CHECK (dataset_id != 'gold' OR is_training_allowed = FALSE)` | None. Even database administrators cannot accidentally update Gold to training allowed without altering table constraints. |
| **`SECURITY DEFINER` Audit Function** | `001_initial_schema.sql` (L245–249) & `003_row_level_security.sql` (L103–108) | `record_annotation_history()` runs as `SECURITY DEFINER` with `SET search_path = public`. Needed execution privilege revocation from `PUBLIC`. | High | PostgreSQL grants `EXECUTE` on functions to `PUBLIC` by default. | Added `REVOKE EXECUTE ON FUNCTION record_annotation_history() FROM PUBLIC, anon; GRANT EXECUTE ... TO authenticated, service_role`. | None. Function cannot be executed by untrusted anonymous callers. |
| **Audit Log Tamper-Resistance** | `001_initial_schema.sql` (L149–168) & `003_row_level_security.sql` (L32–34, L112–114) | `annotation_history` has zero `INSERT`, `UPDATE`, or `DELETE` policies for `authenticated` or `anon`. Writes occur strictly via the `SECURITY DEFINER` trigger. | High (Positive) | Verified RLS policy definitions and table-level privileges. | Added `REVOKE ALL ON TABLE annotation_history FROM PUBLIC, anon, authenticated; GRANT SELECT, INSERT ... TO service_role`. | None. Ordinary users cannot forge, modify, or delete history records. |
| **Service Role Secret Isolation** | `storage.py` (L287–293) & `app.py` | `SUPABASE_SERVICE_ROLE_KEY` is read strictly on the server by Python backend. Never delivered to web clients or static HTML templates. | High (Positive) | Inspected `app.py`, `templates/index.html`, and `storage.py`. | None needed; architecture strictly isolates keys. | None. Browser clients connect via session / Flask API. |
| **Multi-Epoch Protocol Constraints** | `001_initial_schema.sql` (L96–136) | 9 server-side check constraints enforce vocabulary, date window (epoch $\pm 2$ years), confidence $\le 2$ on Landsat, and mandatory notes on `ambiguous`/`other`. | Medium (Positive) | 27 unit tests in `test_supabase_storage_and_migration.py` verify constraint declarations. | Added test assertion for `chk_gold_never_training`. | None. Malformed or invalid classifications cannot be persisted. |
| **Safe Seed Idempotency** | `002_seed_datasets.sql` (L7–28) | `INSERT INTO datasets ... ON CONFLICT (dataset_id) DO UPDATE` explicitly sets `is_training_allowed = FALSE` for `gold`. | Medium (Positive) | Re-execution simulation: Confirmed `is_training_allowed` remains `FALSE` on conflict. | Validated against `chk_gold_never_training`. | None. Re-running migrations cannot weaken Gold holdout status. |

---

## 3. Detailed Technical Analysis

### A. Row Level Security & Privilege Separation
PostgreSQL evaluates table-level permissions prior to Row Level Security. If a role lacks table privileges, the query is rejected immediately; if privileges exist, RLS filters or validates the rows.
- **`anon`:** Has zero write permissions (`REVOKE ALL`). Can only `SELECT` from `datasets` and `samples` to render map interfaces. Cannot query `annotations` or `annotation_history`.
- **`authenticated`:** Can read samples and annotations; can insert and update annotations only when `dataset_id = 't1'`. Has **NO DELETE** privilege and no delete RLS policy.
- **`service_role`:** Has full administrative access for backend jobs, migration tools, and cron workers.
- **Permissive Policy Interaction:** Each role has at most one policy per action (SELECT, INSERT, UPDATE). PostgreSQL does not combine disjoint policies with `OR` across different roles.

### B. Gold Holdout Protection & Research Integrity
- **Write Policy:**
  ```sql
  CREATE POLICY auth_update_t1_annotations ON annotations
      FOR UPDATE TO authenticated
      USING (dataset_id = 't1')
      WITH CHECK (dataset_id = 't1');
  ```
  Both `USING` (target row match) and `WITH CHECK` (post-update row state) require `dataset_id = 't1'`. This prevents:
  1. Modifying existing Gold annotations.
  2. Re-labeling a T1 annotation into Gold.
- **Engine-Level Invariant:**
  ```sql
  CONSTRAINT chk_gold_never_training CHECK (dataset_id != 'gold' OR is_training_allowed = FALSE)
  ```
  Guarantees that `gold` can never be authorized for model training under any circumstance.
- **Fail-Closed Gate in Application:**
  `readiness.py` enforces `overall_decision: BLOCKED` and `is_training_allowed: False` because the full 95.3 GB feature cube (`pune_G30.zarr`) is absent and annotations are at 0.11% completion.

### C. `SECURITY DEFINER` Audit Function Analysis
The trigger function `record_annotation_history()`:
- Specifies `SET search_path = public` to defeat search path poisoning attacks.
- Execution is revoked from `PUBLIC` and `anon` (`REVOKE EXECUTE ... FROM PUBLIC, anon`).
- It is granted strictly to `authenticated` and `service_role` so triggers fire without error on valid annotation writes.
- The destination table `annotation_history` has all privileges revoked from `PUBLIC`, `anon`, and `authenticated`. History records are immutable and append-only via the trigger.

---

## 4. Migration Diffs

```diff
diff --git a/supabase/migrations/20261029000001_001_initial_schema.sql b/supabase/migrations/20261029000001_001_initial_schema.sql
index cf03557..36d219a 100644
--- a/supabase/migrations/20261029000001_001_initial_schema.sql
+++ b/supabase/migrations/20261029000001_001_initial_schema.sql
@@ -17,7 +17,8 @@ CREATE TABLE IF NOT EXISTS datasets (
     is_training_allowed BOOLEAN NOT NULL DEFAULT FALSE,
     total_samples INTEGER NOT NULL DEFAULT 0,
     created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
-    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
+    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
+    CONSTRAINT chk_gold_never_training CHECK (dataset_id != 'gold' OR is_training_allowed = FALSE)
 );
 
 COMMENT ON TABLE datasets IS 'Master registry of reference datasets. Enforces strict training vs evaluation separation.';

diff --git a/supabase/migrations/20261029000003_003_row_level_security.sql b/supabase/migrations/20261029000003_003_row_level_security.sql
index 78cf5fa..9e02693 100644
--- a/supabase/migrations/20261029000003_003_row_level_security.sql
+++ b/supabase/migrations/20261029000003_003_row_level_security.sql
@@ -94,3 +94,38 @@ DROP POLICY IF EXISTS auth_insert_reviews ON quality_reviews;
 CREATE POLICY auth_insert_reviews ON quality_reviews
     FOR INSERT TO authenticated
     WITH CHECK (true);
+
+-- -----------------------------------------------------------------------------
+-- 4. Schema-Level & Table-Level Grants / Hardening (Defense-in-Depth)
+-- -----------------------------------------------------------------------------
+-- Object-level privileges reinforce RLS to prevent permission escalation.
+
+-- Function execution hardening (prevent direct invocation by untrusted roles)
+REVOKE EXECUTE ON FUNCTION record_annotation_history() FROM PUBLIC, anon;
+GRANT EXECUTE ON FUNCTION record_annotation_history() TO authenticated, service_role;
+
+REVOKE EXECUTE ON FUNCTION set_updated_at() FROM PUBLIC, anon;
+GRANT EXECUTE ON FUNCTION set_updated_at() TO authenticated, service_role;
+
+-- Table privileges: Revoke modification privileges from public/anon
+REVOKE ALL ON TABLE annotation_history FROM PUBLIC, anon, authenticated;
+GRANT SELECT, INSERT ON TABLE annotation_history TO service_role;
+
+REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE datasets, samples FROM PUBLIC, anon, authenticated;
+GRANT SELECT ON TABLE datasets, samples TO anon, authenticated;
+GRANT ALL ON TABLE datasets, samples TO service_role;
+
+REVOKE ALL ON TABLE annotations FROM PUBLIC, anon;
+REVOKE DELETE, TRUNCATE ON TABLE annotations FROM authenticated;
+GRANT SELECT, INSERT, UPDATE ON TABLE annotations TO authenticated;
+GRANT ALL ON TABLE annotations TO service_role;
+
+REVOKE ALL ON TABLE quality_reviews FROM PUBLIC, anon;
+REVOKE UPDATE, DELETE, TRUNCATE ON TABLE quality_reviews FROM authenticated;
+GRANT SELECT, INSERT ON TABLE quality_reviews TO authenticated;
+GRANT ALL ON TABLE quality_reviews TO service_role;
+
+-- Sequence usage for ID generation
+GRANT USAGE, SELECT ON SEQUENCE annotations_id_seq, quality_reviews_review_id_seq TO authenticated;
+GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
```

---

## 5. Verification Evidence

1. **Supabase CLI Dry-Run (`npx supabase db push --dry-run`):**
   - Result: **Passed (Exit code 0)**.
   - Identified migrations to push:
     - `20261029000001_001_initial_schema.sql`
     - `20261029000002_002_seed_datasets.sql`
     - `20261029000003_003_row_level_security.sql`
2. **Supabase Schema Linter (`npx supabase db lint --linked`):**
   - Result: **Passed (Exit code 0)**.
   - Output: `No schema errors found`.
3. **Regression Test Suite (`pytest models/ tests/`):**
   - Result: **101 passed in 35.12s (100% green)**.
   - Model 1: 69 passed.
   - Model 2: 12 passed.
   - Model 3: 14 passed.
   - Cross-Model E2E: 6 passed.
4. **Git Status:**
   - Modified tracked migration files and test file; no uncommitted binary files, secrets, or temporary artifacts.

---

## 6. Rollback Limitations & Local Fallback Behavior

- **Remote Database Rollback:**
  Because the remote `public` schema in `bciurjfbrplvruacldsx` currently has 0 application tables, rolling back after migration would simply consist of `DROP TABLE datasets, samples, annotations, annotation_history, quality_reviews CASCADE; DROP FUNCTION record_annotation_history(), set_updated_at();` or `npx supabase db reset --linked`. No historical data exists remotely to be lost.
- **Local Application Fallback:**
  The local system remains configured with `GEOVERSE_STORAGE_BACKEND=json`. All local JSON annotations (`t1_annotations.json`, `gold_annotations.json`) and timestamped backup archives remain completely untouched.

---

## 7. Audit Conclusion

### **READY FOR HUMAN APPROVAL**

The SQL migration files, RLS policies, object privileges, triggers, and constraints have been verified line by line. All identified security gaps have been resolved with hardened, defense-in-depth SQL statements. Dry run and linting have passed with zero errors, and all 101 regression tests are passing.

> [!IMPORTANT]
> In accordance with the **Hard Stop** directive, no remote writes have been executed. Applying the migrations (`npx supabase db push --linked`) awaits your explicit written command:
> **"Deploy migrations"**
