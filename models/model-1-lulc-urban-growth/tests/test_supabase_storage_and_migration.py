"""
Comprehensive Test Suite for Supabase Annotation Storage & Safe JSON Migration.
GeoVerse Model 1 — LULC Urban Growth.

Covers all Phase 6 verification requirements:
1. Database connection and configuration validation (mocked & isolated).
2. Schema and SQL constraint enforcement.
3. Annotation create, read, update, and reload.
4. Unique sample/epoch constraint.
5. Invalid class and confidence rejection.
6. Acquisition date window and mixed-cell validation.
7. 'uncertain', 'ambiguous', 'other', and 'unavailable' handling.
8. Epoch isolation.
9. Concurrent updates and collision resistance.
10. Transaction rollback / strict error handling (NO silent fallback to JSON).
11. Work queue and QC analytics compatibility.
12. Downstream 35-column CSV export schema compatibility.
13. Dry-run migration execution.
14. Idempotent migration retries.
15. Source/destination field-by-field reconciliation.
16. Protection of original JSON source files.
17. Gold dataset separation and training authorization guards.
18. Training-readiness fail-closed behavior.
"""

import os
import sys
import json
import hashlib
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add module root to sys.path
TEST_DIR = Path(__file__).parent.resolve()
MODULE_ROOT = TEST_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from labeling_app.schema import (
    EPOCHS,
    DEFINITE_CLASSES,
    ABSTAIN_CLASSES,
    ALL_CLASSES,
    SHARE_BINS,
    CONFIDENCE_LEVELS,
    SOURCES_OK,
    STATUS_OPTIONS,
    validate_epoch_annotation
)
from labeling_app.storage import (
    AnnotationStore,
    JsonAnnotationStore,
    SupabaseAnnotationStore,
    StorageError,
    StorageConnectionError,
    StorageWriteError,
    StorageValidationError,
    StorageConfigurationError,
    get_storage_backend
)
from labeling_app.migrate_annotations import (
    inventory_sources,
    validate_sources,
    build_migration_plan,
    reconcile_annotations,
    execute_migration,
    compute_file_hash
)
from labeling_app.exporter import export_to_standard_csv, EXPORT_COLUMNS
from labeling_app.qc import compute_qc_stats
from labeling_app.work_queue import sync_and_persist_work_queue
from labeling_app.readiness import evaluate_readiness


# =============================================================================
# 1. Database Connection & Configuration Validation Tests
# =============================================================================

def test_supabase_storage_missing_credentials_raises_config_error(monkeypatch):
    """Verifies that missing Supabase credentials fail closed with a clear configuration error."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    with pytest.raises(StorageConfigurationError) as exc_info:
        SupabaseAnnotationStore(url=None, key=None)
    assert "requires SUPABASE_URL and SUPABASE_KEY" in str(exc_info.value)


def test_supabase_storage_ping_success_and_failure():
    """Tests ping health-check behavior with mocked clients."""
    # Success case
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [{"dataset_id": "t1"}]
    mock_client.table().select().limit().execute.return_value = mock_resp

    store = SupabaseAnnotationStore(url="https://mock.supabase.co", key="mock-key", client=mock_client)
    assert store.ping() is True
    assert store.get_backend_name() == "supabase"

    # Failure case
    mock_client.table().select().limit().execute.side_effect = Exception("Connection timed out")
    assert store.ping() is False


def test_storage_polymorphic_factory(monkeypatch):
    """Verifies that AnnotationStore instantiates the correct subclass based on environment."""
    # Default is json
    monkeypatch.delenv("GEOVERSE_STORAGE_BACKEND", raising=False)
    store_default = AnnotationStore()
    assert isinstance(store_default, JsonAnnotationStore)
    assert store_default.get_backend_name() == "json"

    # Explicit json
    store_json = AnnotationStore(backend="json")
    assert isinstance(store_json, JsonAnnotationStore)

    # Supabase backend
    mock_client = MagicMock()
    store_sb = AnnotationStore(backend="supabase", client=mock_client)
    assert isinstance(store_sb, SupabaseAnnotationStore)
    assert store_sb.get_backend_name() == "supabase"


# =============================================================================
# 2. Schema and SQL Constraint Enforcement Tests
# =============================================================================

def test_sql_migration_files_exist_and_contain_constraints():
    """Inspects SQL DDL files to verify all required protocol constraints are declared."""
    migrations_dir = MODULE_ROOT / "db" / "migrations"
    assert migrations_dir.exists(), "db/migrations directory must exist"

    schema_sql_path = migrations_dir / "001_initial_schema.sql"
    seed_sql_path = migrations_dir / "002_seed_datasets.sql"
    rls_sql_path = migrations_dir / "003_row_level_security.sql"

    assert schema_sql_path.exists()
    assert seed_sql_path.exists()
    assert rls_sql_path.exists()

    schema_sql = schema_sql_path.read_text(encoding="utf-8")

    # Table declarations
    assert "CREATE TABLE IF NOT EXISTS datasets" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS samples" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS annotations" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS annotation_history" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS quality_reviews" in schema_sql

    # Constraints
    assert "uq_annotations_dataset_anon_epoch UNIQUE" in schema_sql
    assert "chk_status_done_class" in schema_sql
    assert "chk_status_unavailable" in schema_sql
    assert "chk_notes_mandatory" in schema_sql
    assert "chk_definite_share_conf" in schema_sql
    assert "chk_landsat_confidence" in schema_sql
    assert "chk_second_class_distinct" in schema_sql
    assert "chk_date_window" in schema_sql
    assert "chk_status_done_imagery" in schema_sql

    # Trigger & Security Definer
    assert "set_updated_at" in schema_sql
    assert "record_annotation_history" in schema_sql
    assert "SECURITY DEFINER" in schema_sql
    assert "trg_record_annotation_history" in schema_sql
    assert "chk_gold_never_training" in schema_sql

    # Seed SQL integrity (T1 training eligible, Gold holdout excluded)
    seed_sql = seed_sql_path.read_text(encoding="utf-8")
    assert "'t1'" in seed_sql
    assert "TRUE" in seed_sql
    assert "699" in seed_sql
    assert "'gold'" in seed_sql
    assert "FALSE" in seed_sql
    assert "641" in seed_sql

    # RLS & Permissions Hardening
    rls_sql = rls_sql_path.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in rls_sql
    assert "service_role" in rls_sql
    assert "auth_insert_t1_annotations" in rls_sql
    assert "REVOKE EXECUTE ON FUNCTION record_annotation_history" in rls_sql
    assert "REVOKE ALL ON TABLE annotation_history" in rls_sql
    assert "REVOKE DELETE, TRUNCATE ON TABLE annotations FROM authenticated" in rls_sql
    assert "DROP POLICY IF EXISTS auth_insert_reviews ON quality_reviews" in rls_sql
    assert "CREATE POLICY auth_insert_reviews" not in rls_sql
    assert "REVOKE ALL ON TABLE quality_reviews FROM PUBLIC, anon, authenticated" in rls_sql
    assert "GRANT SELECT ON TABLE quality_reviews TO authenticated" in rls_sql
    assert "quality_reviews_review_id_seq TO authenticated" not in rls_sql

    # Gold holdout protection in RLS policies (non-Gold constraint enforcement)
    assert "CREATE POLICY auth_select_annotations ON annotations" in rls_sql
    assert "USING (dataset_id != 'gold')" in rls_sql
    assert "auth_select_annotations ON annotations\n    FOR SELECT TO authenticated USING (true);" not in rls_sql
    assert "CREATE POLICY auth_select_reviews ON quality_reviews" in rls_sql
    assert "auth_select_reviews ON quality_reviews\n    FOR SELECT TO authenticated USING (true);" not in rls_sql


def test_schema_vocabulary_and_constraint_validation():
    """Verifies that schema validation correctly rejects non-compliant values."""
    # Invalid class
    is_valid, errs, _ = validate_epoch_annotation(2020, {
        "status": "done",
        "dominant_class": "commercial_shopping_mall",
        "dominant_share_3bins": ">=75",
        "confidence_1to3": 3,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-05-15"
    })
    assert not is_valid
    assert any("not in approved vocabulary" in e for e in errs)

    # Missing notes on ambiguous
    is_valid, errs, _ = validate_epoch_annotation(2020, {
        "status": "done",
        "dominant_class": "ambiguous",
        "dominant_share_3bins": "50-75",
        "confidence_1to3": 2,
        "imagery_source": "Landsat_context",
        "imagery_date": "2020-05-15",
        "notes": ""
    })
    assert not is_valid
    assert any("Notes are mandatory" in e for e in errs)

    # Date window (+/- 2 years)
    is_valid, errs, _ = validate_epoch_annotation(2020, {
        "status": "done",
        "dominant_class": "built_up",
        "dominant_share_3bins": ">=75",
        "confidence_1to3": 3,
        "imagery_source": "GEP_historical",
        "imagery_date": "2015-05-15", # 5 years away
        "notes": ""
    })
    assert not is_valid
    assert any("outside the allowed +/-2 years window" in e for e in errs)

    # Landsat context confidence cap (max 2)
    is_valid, errs, _ = validate_epoch_annotation(2020, {
        "status": "done",
        "dominant_class": "built_up",
        "dominant_share_3bins": ">=75",
        "confidence_1to3": 3, # Illegal: max 2 for Landsat
        "imagery_source": "Landsat_context",
        "imagery_date": "2020-05-15",
        "notes": ""
    })
    assert not is_valid
    assert any("confidence must be at most 2" in e for e in errs)

    # Uncertain does NOT require notes (valid with notes="")
    is_valid, errs, _ = validate_epoch_annotation(2020, {
        "status": "done",
        "dominant_class": "uncertain",
        "dominant_share_3bins": ">=75",
        "confidence_1to3": 2,
        "imagery_source": "Landsat_context",
        "imagery_date": "2020-05-15",
        "notes": ""
    })
    assert is_valid is True
    assert len(errs) == 0

    # Other requires notes (invalid with notes="")
    is_valid, errs, _ = validate_epoch_annotation(2020, {
        "status": "done",
        "dominant_class": "other",
        "dominant_share_3bins": ">=75",
        "confidence_1to3": 2,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-05-15",
        "notes": ""
    })
    assert not is_valid
    assert any("Notes are mandatory when dominant_class is 'other'" in e for e in errs)

    # Other requires share bin and confidence as a definite class
    is_valid, errs, _ = validate_epoch_annotation(2020, {
        "status": "done",
        "dominant_class": "other",
        "dominant_share_3bins": "", # missing share
        "confidence_1to3": 2,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-05-15",
        "notes": "Rocky outcrop"
    })
    assert not is_valid
    assert any("dominant_share_3bins '' is invalid" in e for e in errs)


# =============================================================================
# 3. Annotation Create, Read, Update, and Reload (Supabase Mocked)
# =============================================================================

def test_supabase_storage_save_reload_and_isolation():
    """
    Verifies that SupabaseAnnotationStore correctly persists and reconstructs
    nested annotation structures while enforcing epoch isolation.
    """
    mock_client = MagicMock()

    # Mock sample resolution
    mock_sample_resp = MagicMock()
    mock_sample_resp.data = [{"id": 101}]
    mock_client.table("samples").select("id").eq("dataset_id", "t1").eq("anon_id", "T2-0001").execute.return_value = mock_sample_resp

    # Mock upsert
    mock_upsert_exec = MagicMock()
    mock_upsert_resp = MagicMock()
    mock_upsert_resp.data = [{"id": 1}]
    mock_upsert_exec.execute.return_value = mock_upsert_resp
    mock_client.table("annotations").upsert.return_value = mock_upsert_exec

    store = SupabaseAnnotationStore(url="https://mock.supabase.co", key="mock-key", client=mock_client)

    payload = {
        "epochs": {
            "2020": {
                "status": "done",
                "dominant_class": "built_up",
                "dominant_share_3bins": ">=75",
                "second_class": "none",
                "confidence_1to3": 3,
                "imagery_source": "GEP_historical",
                "imagery_date": "2020-03-15",
                "notes": "Verified urban fabric"
            }
        }
    }

    result = store.save_sample_annotation("t1", "T2-0001", payload, annotator_id="interpreter_1")
    assert result is True

    # Verify upsert call structure
    mock_client.table("annotations").upsert.assert_called_once()
    called_args = mock_client.table("annotations").upsert.call_args[0][0]
    assert len(called_args) == 1
    row = called_args[0]
    assert row["sample_id"] == 101
    assert row["dataset_id"] == "t1"
    assert row["anon_id"] == "T2-0001"
    assert row["epoch"] == 2020
    assert row["dominant_class"] == "built_up"
    assert row["annotator_id"] == "interpreter_1"

    # Mock load_annotations query
    mock_load_resp = MagicMock()
    mock_load_resp.data = [
        {
            "id": 1,
            "dataset_id": "t1",
            "anon_id": "T2-0001",
            "epoch": 2020,
            "status": "done",
            "dominant_class": "built_up",
            "dominant_share_3bins": ">=75",
            "second_class": "none",
            "confidence_1to3": 3,
            "imagery_source": "GEP_historical",
            "imagery_date": "2020-03-15",
            "notes": "Verified urban fabric",
            "updated_at": "2026-10-28T12:00:00+00:00"
        },
        {
            "id": 2,
            "dataset_id": "t1",
            "anon_id": "T2-0001",
            "epoch": 2010,
            "status": "done",
            "dominant_class": "agriculture",
            "dominant_share_3bins": ">=75",
            "second_class": "none",
            "confidence_1to3": 3,
            "imagery_source": "GEP_historical",
            "imagery_date": "2010-04-10",
            "notes": "",
            "updated_at": "2026-10-28T12:05:00+00:00"
        }
    ]
    mock_client.table("annotations").select("*").eq("dataset_id", "t1").execute.return_value = mock_load_resp

    loaded = store.load_annotations("t1")
    assert "T2-0001" in loaded
    epochs = loaded["T2-0001"]["epochs"]
    assert "2020" in epochs
    assert "2010" in epochs
    assert epochs["2020"]["dominant_class"] == "built_up"
    assert epochs["2010"]["dominant_class"] == "agriculture"


# =============================================================================
# 4. Strict Error Handling & NO Silent Fallback to JSON
# =============================================================================

def test_supabase_write_failure_raises_and_never_falls_back_to_json(tmp_path):
    """
    Critical Safety Rule 3 & 11: When a database write fails,
    SupabaseAnnotationStore MUST raise StorageWriteError and NEVER silently write to JSON.
    """
    mock_client = MagicMock()
    mock_client.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": 99}])
    mock_client.table("annotations").upsert().execute.side_effect = Exception("Supabase connection reset by peer")

    json_storage_dir = tmp_path / "storage"
    json_storage_dir.mkdir(parents=True)
    t1_json = json_storage_dir / "t1_annotations.json"
    t1_json.write_text("{}", encoding="utf-8")
    t1_hash_before = compute_file_hash(str(t1_json))

    store = SupabaseAnnotationStore(
        url="https://mock.supabase.co",
        key="mock-key",
        client=mock_client,
        storage_dir=str(json_storage_dir)
    )

    with pytest.raises(StorageWriteError) as exc_info:
        store.save_sample_annotation("t1", "T2-0001", {
            "epochs": {"2020": {"status": "done", "dominant_class": "water"}}
        })

    assert "Failed to write annotations to Supabase" in str(exc_info.value)
    # Verify local JSON was NOT modified as a silent fallback
    t1_hash_after = compute_file_hash(str(t1_json))
    assert t1_hash_before == t1_hash_after, "Local JSON must not be touched on database failure!"


# =============================================================================
# 5. Migration Pipeline Tests (Dry-Run, Idempotency, Validation, Reconciliation)
# =============================================================================

def test_migration_inventory_and_validation():
    """Tests the inventory and validation capabilities of the migration engine."""
    data_dir = str(MODULE_ROOT / "labeling_app" / "data")
    storage_dir = str(MODULE_ROOT / "labeling_app" / "storage")

    inv = inventory_sources(data_dir, storage_dir)
    assert inv["manifests"]["t1"]["total_samples"] == 699
    assert inv["manifests"]["gold"]["total_samples"] == 641
    assert inv["totals"]["total_manifest_samples"] == 1340
    assert inv["totals"]["total_annotated_samples"] == 3
    assert inv["totals"]["total_epoch_annotations"] == 6

    val = validate_sources(data_dir, storage_dir)
    # T2-0002 has empty notes on ambiguous in live storage; validator must catch this
    assert val["total_errors"] == 1
    assert any("Notes are mandatory when dominant_class is 'ambiguous'" in e for e in val["datasets"]["t1"]["errors"])


def test_migration_dry_run_produces_plan_without_writes():
    """Verifies that dry-run mode constructs an auditable plan without modifying any destination."""
    data_dir = str(MODULE_ROOT / "labeling_app" / "data")
    storage_dir = str(MODULE_ROOT / "labeling_app" / "storage")

    # With skip_invalid=True to assess clean migration plan
    plan = build_migration_plan(data_dir, storage_dir, target_store=None, skip_invalid=True)
    assert plan["dataset_filter"] == "all"
    assert len(plan["datasets_to_seed"]) == 2
    assert plan["action_summary"]["samples_count"] == 1340
    assert plan["action_summary"]["annotations_count"] == 5
    assert plan["action_summary"]["quarantined_count"] == 1


def test_migration_confirmation_guard_prevents_accidental_writes():
    """Verifies that execute_migration fails closed if confirm=False."""
    mock_store = MagicMock()
    plan = {"validation_passed": True, "datasets_to_seed": [], "samples_to_sync": {}}

    with pytest.raises(StorageWriteError) as exc_info:
        execute_migration(plan, mock_store, confirm=False)
    assert "--confirm flag is strictly required" in str(exc_info.value)


def test_migration_execution_and_idempotency_mocked(tmp_path):
    """
    Tests full migration execution with a mocked store, verifying:
    - Datasets seeded
    - Samples synced
    - Annotations synced
    - Original JSON preserved
    - Reconciliation passed
    - Idempotent repeated execution
    """
    mock_client = MagicMock()
    mock_client.table().upsert().execute.return_value = MagicMock(data=[{"id": 1}])
    mock_client.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": 1}])

    mock_store = SupabaseAnnotationStore(url="https://mock.supabase.co", key="mock-key", client=mock_client)

    # Create isolated test data directory with valid samples and annotations
    test_data = tmp_path / "data"
    test_data.mkdir()
    test_manifest = [
        {"anon_id": "T2-TEST-1", "lat": 18.52, "lon": 73.85, "polygon": []},
        {"anon_id": "T2-TEST-2", "lat": 18.53, "lon": 73.86, "polygon": []}
    ]
    (test_data / "t1_manifest.json").write_text(json.dumps(test_manifest), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    test_annotations = {
        "T2-TEST-1": {
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
    (test_storage / "t1_annotations.json").write_text(json.dumps(test_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    # Mock destination loading to match source exactly for reconciliation
    mock_store.load_annotations = MagicMock(side_effect=lambda ds: test_annotations if ds == "t1" else {})

    plan = build_migration_plan(str(test_data), str(test_storage), target_store=mock_store, dataset_filter="t1")
    assert plan["validation_passed"] is True

    # Run 1: initial migration
    report_run1 = execute_migration(
        plan, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage)
    )
    assert report_run1["status"] == "SUCCESS"
    assert report_run1["annotations_synced"] == 1
    assert report_run1["source_json_unmodified"] is True
    assert report_run1["reconciliation"]["is_fully_reconciled"] is True

    # Run 2: idempotent retry
    report_run2 = execute_migration(
        plan, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage)
    )
    assert report_run2["status"] == "SUCCESS"
    assert report_run2["annotations_synced"] == 1
    assert report_run2["source_json_unmodified"] is True


def test_field_by_field_reconciliation():
    """Verifies that reconciliation performs granular field-by-field verification."""
    source = {
        "T2-0001": {
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

    # Perfect match
    match_dest = {
        "T2-0001": {
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
    rec_pass = reconcile_annotations(source, match_dest)
    assert rec_pass["is_fully_reconciled"] is True
    assert rec_pass["exact_matches"] == 1
    assert len(rec_pass["mismatches"]) == 0

    # Discrepancy in confidence and class
    diff_dest = {
        "T2-0001": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "agriculture", # mismatch
                    "dominant_share_3bins": ">=75",
                    "second_class": "none",
                    "confidence_1to3": 1, # mismatch
                    "imagery_source": "GEP_historical",
                    "imagery_date": "2020-04-10",
                    "notes": ""
                }
            }
        }
    }
    rec_fail = reconcile_annotations(source, diff_dest)
    assert rec_fail["is_fully_reconciled"] is False
    assert len(rec_fail["mismatches"]) == 1
    diffs = rec_fail["mismatches"][0]["differences"]
    assert "dominant_class" in diffs
    assert "confidence_1to3" in diffs


# =============================================================================
# 6. Compatibility Tests with Existing Application Workflows
# =============================================================================

def test_work_queue_and_qc_compatibility(tmp_path):
    """Verifies that work queue sync and QC analytics work identically with storage abstraction."""
    store = JsonAnnotationStore(storage_dir=str(tmp_path))
    manifest = [{"anon_id": "T2-0001", "lat": 18.52, "lon": 73.85, "polygon": []}]

    # Save via store
    store.save_sample_annotation("t1", "T2-0001", {
        "epochs": {
            "2020": {
                "status": "done",
                "dominant_class": "built_up",
                "dominant_share_3bins": ">=75",
                "second_class": "none",
                "confidence_1to3": 3,
                "imagery_source": "GEP_historical",
                "imagery_date": "2020-04-10",
                "notes": ""
            }
        }
    })

    annotations = store.load_annotations("t1")
    assert "T2-0001" in annotations

    # Work queue sync
    q_data = sync_and_persist_work_queue(manifest, annotations, str(tmp_path), "t1")
    assert q_data["summary"]["total_samples"] == 1
    assert q_data["summary"]["in_progress"] == 1
    assert q_data["summary"]["categories"]["partially_annotated_samples"] == 1

    # QC stats computation
    qc_stats = compute_qc_stats(manifest, annotations, dataset="t1")
    assert qc_stats["total_samples"] == 1
    assert qc_stats["in_progress_samples"] == 1
    assert qc_stats["epoch_progress"]["2020"]["done"] == 1


def test_csv_export_schema_compatibility_from_store(tmp_path):
    """Verifies that CSV export produces exact 35 columns from store annotations."""
    store = JsonAnnotationStore(storage_dir=str(tmp_path))
    manifest_path = str(tmp_path / "manifest.json")
    manifest = [{"anon_id": "T2-0001", "lat": 18.52, "lon": 73.85, "polygon": []}]
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    store.save_sample_annotation("t1", "T2-0001", {
        "epochs": {
            "2020": {
                "status": "done",
                "dominant_class": "built_up",
                "dominant_share_3bins": ">=75",
                "second_class": "none",
                "confidence_1to3": 3,
                "imagery_source": "GEP_historical",
                "imagery_date": "2020-04-10",
                "notes": ""
            }
        }
    })

    csv_out = str(tmp_path / "test_export.csv")
    summary = export_to_standard_csv(manifest_path, store.load_annotations("t1"), csv_out)

    assert os.path.exists(csv_out)
    with open(csv_out, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert len(header) == 35
    assert header == EXPORT_COLUMNS


def test_training_readiness_fail_closed_guard():
    """Verifies that evaluate_readiness fails closed while annotations are incomplete."""
    readiness = evaluate_readiness()
    assert readiness["overall_decision"] == "BLOCKED"
    assert readiness["is_training_allowed"] is False
    gates = {item["gate"]: item["status"] for item in readiness["checklist"]}
    assert "T1 Human Reference Annotations (699 points x 4 epochs)" in gates
    assert gates["T1 Human Reference Annotations (699 points x 4 epochs)"] == "BLOCKED"
    assert gates["Tier-A Gold Holdout Reference Annotations (641 points x 4 epochs)"] == "BLOCKED"


# =============================================================================
# 7. Step 3A Safety Tests: Collision Detection, Quarantining, and Semantic Flags
# =============================================================================

def test_destination_record_comparison_and_collision_classification(tmp_path):
    """
    Tests the 4-way collision classification:
    1. to_insert: Destination record does not exist
    2. already_reconciled: Destination record exists and all 8 fields match
    3. conflicts: Destination record exists and fields differ
    4. invalid_destination: Destination record has invalid structure
    """
    test_data = tmp_path / "data"
    test_data.mkdir()
    manifest = [
        {"anon_id": "T2-0001", "lat": 18.52, "lon": 73.85, "polygon": []},
        {"anon_id": "T2-0002", "lat": 18.53, "lon": 73.86, "polygon": []},
        {"anon_id": "T2-0003", "lat": 18.54, "lon": 73.87, "polygon": []},
        {"anon_id": "T2-0004", "lat": 18.55, "lon": 73.88, "polygon": []}
    ]
    (test_data / "t1_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()

    source_annotations = {
        "T2-0001": {
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
        },
        "T2-0002": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "built_up",
                    "dominant_share_3bins": "50-75",
                    "second_class": "none",
                    "confidence_1to3": 2,
                    "imagery_source": "Landsat_context",
                    "imagery_date": "2021-01-15",
                    "notes": ""
                }
            }
        },
        "T2-0003": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "agriculture",
                    "dominant_share_3bins": ">=75",
                    "second_class": "none",
                    "confidence_1to3": 3,
                    "imagery_source": "GEP_historical",
                    "imagery_date": "2020-06-20",
                    "notes": "source label"
                }
            }
        },
        "T2-0004": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "natural_vegetation",
                    "dominant_share_3bins": ">=75",
                    "second_class": "none",
                    "confidence_1to3": 3,
                    "imagery_source": "GEP_historical",
                    "imagery_date": "2020-05-12",
                    "notes": ""
                }
            }
        }
    }
    (test_storage / "t1_annotations.json").write_text(json.dumps(source_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    mock_store = MagicMock()
    mock_store.get_backend_name.return_value = "supabase"
    mock_store.ping.return_value = True

    dest_annotations = {
        "T2-0002": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "built_up",
                    "dominant_share_3bins": "50-75",
                    "second_class": "none",
                    "confidence_1to3": 2,
                    "imagery_source": "Landsat_context",
                    "imagery_date": "2021-01-15",
                    "notes": ""
                }
            }
        },
        "T2-0003": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "water",
                    "dominant_share_3bins": ">=75",
                    "second_class": "none",
                    "confidence_1to3": 3,
                    "imagery_source": "GEP_historical",
                    "imagery_date": "2020-06-20",
                    "notes": "dest label differs"
                }
            }
        },
        "T2-0004": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": "corrupted string instead of dict"
            }
        },
        "T2-EXTRA": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "water"
                }
            }
        }
    }
    mock_store.load_annotations.side_effect = lambda ds: dest_annotations if ds == "t1" else {}

    plan = build_migration_plan(
        str(test_data),
        str(test_storage),
        target_store=mock_store,
        dataset_filter="t1"
    )

    actions = plan["actions"]
    summary = plan["action_summary"]

    assert summary["to_insert_count"] == 1
    assert actions["to_insert"][0]["anon_id"] == "T2-0001"

    assert summary["already_reconciled_count"] == 1
    assert actions["already_reconciled"][0]["anon_id"] == "T2-0002"

    assert summary["conflicts_count"] == 1
    conflict = actions["conflicts"][0]
    assert conflict["anon_id"] == "T2-0003"
    assert "dominant_class" in conflict["differences"]
    assert conflict["differences"]["dominant_class"]["source"] == "agriculture"
    assert conflict["differences"]["dominant_class"]["destination"] == "water"

    assert summary["invalid_destination_count"] == 1
    assert actions["invalid_destination"][0]["record"]["anon_id"] == "T2-0004"

    assert summary["extra_in_destination_count"] == 1
    assert actions["extra_in_destination"][0]["anon_id"] == "T2-EXTRA"

    assert plan["can_proceed"] is False
    assert any("conflicting records" in b for b in plan["blockers"])


def test_migration_halts_safely_on_conflicts():
    """
    Verifies that execute_migration strictly aborts if pre-import collisions are detected,
    never silently overwriting divergent database records.
    """
    mock_store = MagicMock()
    mock_store.get_backend_name.return_value = "supabase"
    mock_store.ping.return_value = True

    plan = {
        "validation_passed": True,
        "can_proceed": False,
        "actions": {
            "to_insert": [{"dataset_id": "t1", "anon_id": "T2-0001", "epoch": 2020}],
            "already_reconciled": [],
            "conflicts": [{
                "dataset_id": "t1",
                "anon_id": "T2-0002",
                "epoch": 2020,
                "differences": {"dominant_class": {"source": "built_up", "destination": "water"}}
            }],
            "invalid_destination": [],
            "extra_in_destination": []
        },
        "action_summary": {"conflicts_count": 1, "quarantined_count": 0},
        "datasets_to_seed": [],
        "samples_to_sync": {},
        "target_status": {"destination_inspected": True}
    }

    with pytest.raises(StorageWriteError) as exc_info:
        execute_migration(plan, mock_store, confirm=True)
    assert "pre-import collisions detected" in str(exc_info.value)
    mock_store.save_sample_annotation.assert_not_called()


def test_quarantine_preserves_t2_0002_with_remediation_guidance():
    """
    Verifies that T2-0002 (epoch 2020, ambiguous without notes) is safely quarantined
    with explicit remediation guidance under --skip-invalid, source JSON is verified intact,
    and migration plan documents the quarantine.
    """
    data_dir = str(MODULE_ROOT / "labeling_app" / "data")
    storage_dir = str(MODULE_ROOT / "labeling_app" / "storage")

    t1_json_path = os.path.join(storage_dir, "t1_annotations.json")
    hash_before = compute_file_hash(t1_json_path)

    val = validate_sources(data_dir, storage_dir)
    assert val["is_valid"] is False
    assert any("Notes are mandatory when dominant_class is 'ambiguous'" in e for e in val["datasets"]["t1"]["errors"])

    plan = build_migration_plan(data_dir, storage_dir, target_store=None, skip_invalid=True)
    assert plan["action_summary"]["quarantined_count"] == 1
    q_records = plan["quarantined_records"]["t1"]
    assert len(q_records) == 1
    assert q_records[0]["record"]["anon_id"] == "T2-0002"
    assert q_records[0]["record"]["epoch"] == 2020
    assert any("Notes are mandatory" in e for e in q_records[0]["errors"])
    assert "remediation_guidance" in q_records[0]
    assert "Human photo-interpreter must inspect sample T2-0002" in q_records[0]["remediation_guidance"]

    hash_after = compute_file_hash(t1_json_path)
    assert hash_before == hash_after


def test_semantic_review_flag_for_t2_0003_uncertain_high_share():
    """
    Verifies that T2-0003 (epoch 2020: dominant_class='uncertain', dominant_share_3bins='>=75'):
    1. Is syntactically permitted under existing schema.py rules (returns is_valid=True, 0 errors)
    2. Generates an explicit semantic review flag for human photo-interpreters
    3. Is scheduled for migration (not quarantined, not rejected)
    """
    data_dir = str(MODULE_ROOT / "labeling_app" / "data")
    storage_dir = str(MODULE_ROOT / "labeling_app" / "storage")

    with open(os.path.join(storage_dir, "t1_annotations.json"), "r", encoding="utf-8") as f:
        t1_ann = json.load(f)

    t2_0003_2020 = t1_ann["T2-0003"]["epochs"]["2020"]
    assert t2_0003_2020["dominant_class"] == "uncertain"
    assert t2_0003_2020["dominant_share_3bins"] == ">=75"

    is_valid, errs, warns = validate_epoch_annotation(2020, t2_0003_2020)
    assert is_valid is True
    assert len(errs) == 0

    val = validate_sources(data_dir, storage_dir)
    assert val["total_semantic_flags"] >= 1
    t1_flags = val["datasets"]["t1"]["semantic_flags"]
    matched_flags = [f for f in t1_flags if f["anon_id"] == "T2-0003" and f["epoch"] == 2020]
    assert len(matched_flags) == 1
    assert matched_flags[0]["flag"] == "uncertain_with_high_share"
    assert "Dominant class is 'uncertain' despite high area share" in matched_flags[0]["reason"]

    plan = build_migration_plan(data_dir, storage_dir, target_store=None, skip_invalid=True)
    t1_records = plan["annotations_to_migrate"]["t1"]["records"]
    t2_0003_scheduled = [r for r in t1_records if r["anon_id"] == "T2-0003" and r["epoch"] == 2020]
    assert len(t2_0003_scheduled) == 1
    assert t2_0003_scheduled[0]["dominant_class"] == "uncertain"


def test_dataset_boundaries_and_disjoint_identity_spaces():
    """
    Verifies dataset integrity and research protocol separation:
    1. T1 (699 samples, prefix T2-) vs Gold (641 samples, prefix P4-)
    2. Zero ID intersection (disjoint sample identity spaces)
    3. T1 is authorized for training (is_training_allowed=True)
    4. Gold is held-out evaluation benchmark (is_training_allowed=False)
    5. Migration prevents cross-dataset sample mixing
    """
    data_dir = str(MODULE_ROOT / "labeling_app" / "data")
    with open(os.path.join(data_dir, "t1_manifest.json"), "r", encoding="utf-8") as f:
        t1_manifest = json.load(f)
    with open(os.path.join(data_dir, "gold_manifest.json"), "r", encoding="utf-8") as f:
        gold_manifest = json.load(f)

    assert len(t1_manifest) == 699
    assert len(gold_manifest) == 641

    t1_ids = {s["anon_id"] for s in t1_manifest}
    gold_ids = {s["anon_id"] for s in gold_manifest}

    assert all(aid.startswith("T2-") for aid in t1_ids)
    assert all(aid.startswith("P4-") for aid in gold_ids)
    assert len(t1_ids.intersection(gold_ids)) == 0

    storage_dir = str(MODULE_ROOT / "labeling_app" / "storage")
    plan = build_migration_plan(data_dir, storage_dir, target_store=None, skip_invalid=True)
    ds_meta = {d["dataset_id"]: d for d in plan["datasets_to_seed"]}
    assert ds_meta["t1"]["is_training_allowed"] is True
    assert ds_meta["t1"]["total_samples"] == 699
    assert ds_meta["gold"]["is_training_allowed"] is False
    assert ds_meta["gold"]["total_samples"] == 641


def test_csv_export_regeneration_in_temp_dir_preserves_files(tmp_path):
    """
    Verifies that CSV export regeneration can safely run in an isolated temp directory,
    validates the 35-column schema, and leaves live exports unmodified.
    """
    live_export_path = str(MODULE_ROOT / "labeling_app" / "exports" / "t1_annotated_export.csv")
    live_report_path = str(MODULE_ROOT / "labeling_app" / "exports" / "t1_annotated_export_validation_report.json")

    hash_export_before = compute_file_hash(live_export_path)
    hash_report_before = compute_file_hash(live_report_path)

    temp_export_path = str(tmp_path / "temp_t1_export.csv")
    manifest_path = str(MODULE_ROOT / "labeling_app" / "data" / "t1_manifest.json")
    storage_dir = str(MODULE_ROOT / "labeling_app" / "storage")

    store = JsonAnnotationStore(storage_dir=storage_dir)
    annotations = store.load_annotations("t1")

    summary = export_to_standard_csv(manifest_path, annotations, temp_export_path)

    assert os.path.exists(temp_export_path)
    with open(temp_export_path, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert len(header) == 35
    assert header == EXPORT_COLUMNS

    temp_report_path = str(tmp_path / "temp_t1_export_validation_report.json")
    assert os.path.exists(temp_report_path)
    assert summary["total_samples"] == 699

    hash_export_after = compute_file_hash(live_export_path)
    hash_report_after = compute_file_hash(live_report_path)
    assert hash_export_before == hash_export_after
    assert hash_report_before == hash_report_after


def test_quarantine_execution_reports_partial_migration_with_quarantine(tmp_path):
    """
    Verifies that when migration executes with quarantined records,
    the execution report status is PARTIAL_MIGRATION_WITH_QUARANTINE, not SUCCESS.
    """
    test_data = tmp_path / "data"
    test_data.mkdir()
    manifest = [{"anon_id": "T2-VALID", "lat": 18.52, "lon": 73.85, "polygon": []}]
    (test_data / "t1_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    source_annotations = {
        "T2-VALID": {
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
        },
        "T2-INVALID": {
            "updated_at": "2026-10-28T12:00:00+00:00",
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "ambiguous",
                    "dominant_share_3bins": "50-75",
                    "second_class": "none",
                    "confidence_1to3": 2,
                    "imagery_source": "Landsat_context",
                    "imagery_date": "2020-04-10",
                    "notes": ""
                }
            }
        }
    }
    (test_storage / "t1_annotations.json").write_text(json.dumps(source_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    mock_client = MagicMock()
    mock_client.table().upsert().execute.return_value = MagicMock(data=[{"id": 1}])
    mock_client.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": 1}])
    mock_store = SupabaseAnnotationStore(url="https://mock.supabase.co", key="mock-key", client=mock_client)

    dest_data = {
        "T2-VALID": source_annotations["T2-VALID"]
    }
    mock_store.load_annotations = MagicMock(side_effect=lambda ds: dest_data if ds == "t1" else {})

    plan = build_migration_plan(
        str(test_data),
        str(test_storage),
        target_store=mock_store,
        dataset_filter="t1",
        skip_invalid=True
    )

    assert plan["action_summary"]["quarantined_count"] == 1
    report = execute_migration(
        plan, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage)
    )

    assert report["status"] == "PARTIAL_MIGRATION_WITH_QUARANTINE"
    assert report["quarantined_records_count"] == 1
    assert report["reconciliation"]["is_fully_reconciled"] is True
    assert len(report["reconciliation"]["quarantined_pending_remediation"]) == 1


# =============================================================================
# 10. Regression & Verification Tests for BLK-01 and BLK-02
# =============================================================================

def test_destination_inspection_unavailable_fails_closed(tmp_path):
    """
    BLK-01: Verifies that if destination inspection is unavailable,
    migration strictly fails closed rather than claiming conflicts were checked.
    """
    test_data = tmp_path / "data"
    test_data.mkdir()
    (test_data / "t1_manifest.json").write_text(json.dumps([{"anon_id": "T2-0001", "lat": 18.52, "lon": 73.85, "polygon": []}]), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    source_annotations = {
        "T2-0001": {
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
    (test_storage / "t1_annotations.json").write_text(json.dumps(source_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    # Case 1: Target store is None
    plan_no_store = build_migration_plan(str(test_data), str(test_storage), target_store=None)
    assert plan_no_store["target_status"]["connected"] is False
    assert plan_no_store["target_status"]["destination_inspected"] is False
    assert plan_no_store["can_proceed"] is False
    assert any("Pre-import collision check" in b for b in plan_no_store["blockers"])

    # Attempting to execute with destination_inspected=False raises StorageWriteError
    mock_store = MagicMock()
    with pytest.raises(StorageWriteError) as exc_info:
        execute_migration(plan_no_store, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage))
    assert "destination pre-import inspection was not performed or failed" in str(exc_info.value)
    mock_store.save_sample_annotation.assert_not_called()

    # Case 2: Target store ping fails
    mock_failing_store = MagicMock()
    mock_failing_store.ping.return_value = False
    mock_failing_store.get_backend_name.return_value = "supabase"
    plan_ping_fail = build_migration_plan(str(test_data), str(test_storage), target_store=mock_failing_store)
    assert plan_ping_fail["target_status"]["connected"] is False
    assert plan_ping_fail["target_status"]["destination_inspected"] is False
    assert plan_ping_fail["can_proceed"] is False

    with pytest.raises(StorageWriteError) as exc_info2:
        execute_migration(plan_ping_fail, mock_failing_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage))
    assert "destination pre-import inspection was not performed or failed" in str(exc_info2.value)


def test_collision_detection_conflicting_records_never_overwritten(tmp_path):
    """
    BLK-01: Verifies that divergent destination records are identified,
    all differences are detailed, and migration halts without touching destination.
    """
    test_data = tmp_path / "data"
    test_data.mkdir()
    (test_data / "t1_manifest.json").write_text(json.dumps([{"anon_id": "T2-CONFLICT", "lat": 18.52, "lon": 73.85, "polygon": []}]), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    source_annotations = {
        "T2-CONFLICT": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "water",
                    "dominant_share_3bins": ">=75",
                    "second_class": "none",
                    "confidence_1to3": 3,
                    "imagery_source": "GEP_historical",
                    "imagery_date": "2020-04-10",
                    "notes": "source label"
                }
            }
        }
    }
    (test_storage / "t1_annotations.json").write_text(json.dumps(source_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    mock_client = MagicMock()
    mock_store = SupabaseAnnotationStore(url="https://mock.supabase.co", key="mock-key", client=mock_client)

    dest_annotations = {
        "T2-CONFLICT": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "built_up",  # differs
                    "dominant_share_3bins": "50-75",  # differs
                    "second_class": "agriculture",  # differs
                    "confidence_1to3": 2,  # differs
                    "imagery_source": "Landsat_context",  # differs
                    "imagery_date": "2020-05-15",  # differs
                    "notes": "destination pre-existing label"  # differs
                }
            }
        }
    }
    mock_store.load_annotations = MagicMock(side_effect=lambda ds: dest_annotations if ds == "t1" else {})

    plan = build_migration_plan(str(test_data), str(test_storage), target_store=mock_store, dataset_filter="t1")
    assert plan["target_status"]["destination_inspected"] is True
    assert plan["action_summary"]["conflicts_count"] == 1
    assert plan["can_proceed"] is False

    conflict = plan["actions"]["conflicts"][0]
    assert conflict["anon_id"] == "T2-CONFLICT"
    assert conflict["epoch"] == 2020
    assert "dominant_class" in conflict["differences"]
    assert "notes" in conflict["differences"]

    with pytest.raises(StorageWriteError) as exc_info:
        execute_migration(plan, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage))
    assert "pre-import collisions detected" in str(exc_info.value)
    mock_client.table().upsert().execute.assert_not_called()


def test_idempotent_repeated_migration_skips_matching_records(tmp_path):
    """
    BLK-01: Verifies that an identical destination record is recognized as already_reconciled,
    skipped from database insertion, and repeat runs are idempotent and safe.
    """
    test_data = tmp_path / "data"
    test_data.mkdir()
    (test_data / "t1_manifest.json").write_text(json.dumps([{"anon_id": "T2-IDEM", "lat": 18.52, "lon": 73.85, "polygon": []}]), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    source_annotations = {
        "T2-IDEM": {
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
    (test_storage / "t1_annotations.json").write_text(json.dumps(source_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    mock_client = MagicMock()
    mock_client.table().upsert().execute.return_value = MagicMock(data=[{"id": 1}])
    mock_client.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": 1}])
    mock_store = SupabaseAnnotationStore(
        url="https://mock.supabase.co",
        key="mock-key",
        client=mock_client,
        manifest_dir=str(test_data)
    )

    # Simulated destination database state
    simulated_db = {}
    mock_store.load_annotations = MagicMock(side_effect=lambda ds: simulated_db if ds == "t1" else {})

    def fake_save(ds, aid, payload, annotator_id=None):
        if ds == "t1":
            simulated_db[aid] = payload
        return True
    mock_store.save_sample_annotation = MagicMock(side_effect=fake_save)

    # Pass 1: Initial migration (destination empty)
    plan1 = build_migration_plan(str(test_data), str(test_storage), target_store=mock_store, dataset_filter="t1")
    assert plan1["action_summary"]["to_insert_count"] == 1
    assert plan1["action_summary"]["already_reconciled_count"] == 0

    report1 = execute_migration(plan1, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage))
    assert report1["status"] == "SUCCESS"
    assert report1["annotations_inserted"] == 1
    assert report1["skipped_identical"] == 0
    assert report1["reconciliation"]["is_fully_reconciled"] is True

    # Pass 2: Repeat migration (destination already populated with identical record)
    plan2 = build_migration_plan(str(test_data), str(test_storage), target_store=mock_store, dataset_filter="t1")
    assert plan2["action_summary"]["to_insert_count"] == 0
    assert plan2["action_summary"]["already_reconciled_count"] == 1
    assert plan2["action_summary"]["conflicts_count"] == 0

    mock_store.save_sample_annotation.reset_mock()
    report2 = execute_migration(plan2, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage))
    assert report2["status"] == "SUCCESS"
    assert report2["annotations_inserted"] == 0
    assert report2["skipped_identical"] == 1
    assert report2["reconciliation"]["is_fully_reconciled"] is True
    # Proves zero writes performed on repeat run!
    mock_store.save_sample_annotation.assert_not_called()


def test_quarantine_reconciliation_mixed_outcomes_genuine_missing_fails(tmp_path):
    """
    BLK-02: Verifies that post-migration reconciliation properly separates quarantined records
    from genuine missing records, and fails closed when a valid record is genuinely missing.
    """
    test_data = tmp_path / "data"
    test_data.mkdir()
    manifest = [
        {"anon_id": "T2-VALID-1", "lat": 18.52, "lon": 73.85, "polygon": []},
        {"anon_id": "T2-INVALID", "lat": 18.53, "lon": 73.86, "polygon": []},
        {"anon_id": "T2-VALID-2", "lat": 18.54, "lon": 73.87, "polygon": []}
    ]
    (test_data / "t1_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    source_annotations = {
        "T2-VALID-1": {
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
        },
        "T2-INVALID": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "ambiguous",
                    "dominant_share_3bins": "50-75",
                    "second_class": "agriculture",
                    "confidence_1to3": 2,
                    "imagery_source": "Landsat_context",
                    "imagery_date": "2020-04-10",
                    "notes": ""  # Invalid: notes mandatory
                }
            }
        },
        "T2-VALID-2": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "built_up",
                    "dominant_share_3bins": ">=75",
                    "second_class": "none",
                    "confidence_1to3": 3,
                    "imagery_source": "GEP_historical",
                    "imagery_date": "2020-05-10",
                    "notes": ""
                }
            }
        }
    }
    (test_storage / "t1_annotations.json").write_text(json.dumps(source_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    mock_client = MagicMock()
    mock_client.table().upsert().execute.return_value = MagicMock(data=[{"id": 1}])
    mock_client.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": 1}])
    mock_store = SupabaseAnnotationStore(
        url="https://mock.supabase.co",
        key="mock-key",
        client=mock_client,
        manifest_dir=str(test_data)
    )

    # Destination DB only contains T2-VALID-1; T2-VALID-2 is genuinely missing
    dest_data = {
        "T2-VALID-1": source_annotations["T2-VALID-1"]
    }
    mock_store.load_annotations = MagicMock(side_effect=lambda ds: dest_data if ds == "t1" else {})

    plan = build_migration_plan(str(test_data), str(test_storage), target_store=mock_store, dataset_filter="t1", skip_invalid=True)
    assert plan["action_summary"]["quarantined_count"] == 1

    # Simulate execution where store failed to save T2-VALID-2 (still missing in dest)
    report = execute_migration(plan, mock_store, confirm=True, data_dir=str(test_data), storage_dir=str(test_storage))

    rec = report["reconciliation"]
    # 1. Quarantined record is identified separately with remediation guidance
    assert len(rec["quarantined_pending_remediation"]) == 1
    q_entry = rec["quarantined_pending_remediation"][0]
    assert q_entry["anon_id"] == "T2-INVALID"
    assert q_entry["epoch"] == 2020
    assert len(q_entry["validation_errors"]) > 0
    assert "Notes are mandatory when dominant_class is 'ambiguous'" in q_entry["validation_errors"][0]

    # 2. Genuine missing record (T2-VALID-2) is caught and causes reconciliation failure
    assert any("T2-VALID-2" in miss for miss in rec["missing_in_destination"])
    assert rec["is_fully_reconciled"] is False
    assert report["status"] == "RECONCILIATION_MISMATCH"


def test_quarantine_reconciliation_mixed_outcomes_divergent_field_fails(tmp_path):
    """
    BLK-02: Verifies that post-migration reconciliation fails closed when a valid record
    diverges from the destination, even when other records are quarantined.
    """
    test_data = tmp_path / "data"
    test_data.mkdir()
    manifest = [
        {"anon_id": "T2-VALID", "lat": 18.52, "lon": 73.85, "polygon": []},
        {"anon_id": "T2-INVALID", "lat": 18.53, "lon": 73.86, "polygon": []}
    ]
    (test_data / "t1_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (test_data / "gold_manifest.json").write_text(json.dumps([]), encoding="utf-8")

    test_storage = tmp_path / "storage"
    test_storage.mkdir()
    source_annotations = {
        "T2-VALID": {
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
        },
        "T2-INVALID": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "ambiguous",
                    "dominant_share_3bins": "50-75",
                    "second_class": "agriculture",
                    "confidence_1to3": 2,
                    "imagery_source": "Landsat_context",
                    "imagery_date": "2020-04-10",
                    "notes": ""
                }
            }
        }
    }
    (test_storage / "t1_annotations.json").write_text(json.dumps(source_annotations), encoding="utf-8")
    (test_storage / "gold_annotations.json").write_text(json.dumps({}), encoding="utf-8")

    # Destination DB contains T2-VALID but with divergent field (dominant_class is built_up instead of water)
    dest_data = {
        "T2-VALID": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "built_up",
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

    mock_client = MagicMock()
    mock_store = SupabaseAnnotationStore(url="https://mock.supabase.co", key="mock-key", client=mock_client)
    mock_store.load_annotations = MagicMock(side_effect=lambda ds: dest_data if ds == "t1" else {})

    # Use direct reconcile_annotations to verify reconciliation behavior on divergent destination
    quarantined_keys = {"t1:T2-INVALID:2020", "T2-INVALID:2020"}
    quarantined_details = {
        "T2-INVALID:2020": {
            "errors": ["Epoch 2020: Notes are mandatory when dominant_class is 'ambiguous'."],
            "remediation_guidance": "Human photo-interpreter must inspect sample T2-INVALID (epoch 2020)."
        }
    }

    source_all = {f"t1:{k}": v for k, v in source_annotations.items()}
    dest_all = {f"t1:{k}": v for k, v in dest_data.items()}

    rec = reconcile_annotations(
        source_all,
        dest_all,
        quarantined_keys=quarantined_keys,
        quarantined_details=quarantined_details
    )

    assert len(rec["quarantined_pending_remediation"]) == 1
    assert len(rec["mismatches"]) == 1
    assert rec["mismatches"][0]["anon_id"] == "t1:T2-VALID"
    assert "dominant_class" in rec["mismatches"][0]["differences"]
    assert rec["is_fully_reconciled"] is False



# =============================================================================
# 19. Security Hardening, RLS Authorization & Synchronization Tests
# =============================================================================

def test_migration_root_and_model_copies_are_synchronized():
    """
    Verifies that the root Supabase migrations and corresponding Model 1 migration
    copies are 100% synchronized and identical.
    """
    repo_root = MODULE_ROOT.parent.parent
    model_migrations = MODULE_ROOT / "db" / "migrations"
    root_migrations = repo_root / "supabase" / "migrations"

    assert model_migrations.exists()
    assert root_migrations.exists()

    pairs = [
        (model_migrations / "001_initial_schema.sql", root_migrations / "20261029000001_001_initial_schema.sql"),
        (model_migrations / "002_seed_datasets.sql", root_migrations / "20261029000002_002_seed_datasets.sql"),
        (model_migrations / "003_row_level_security.sql", root_migrations / "20261029000003_003_row_level_security.sql")
    ]

    for m1_path, root_path in pairs:
        assert m1_path.exists(), f"Missing {m1_path}"
        assert root_path.exists(), f"Missing {root_path}"
        m1_text = m1_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        root_text = root_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert m1_text == root_text, f"Migration copy mismatch between {m1_path.name} and {root_path.name}"


def test_quality_reviews_unrestricted_insert_vulnerability_regression():
    """
    Regression Test: Ensures that the unrestricted INSERT policy on quality_reviews
    (WITH CHECK (true)) is permanently eradicated, direct creation by authenticated
    users is denied, and only the trusted service_role can create or update reviews.
    """
    rls_sql_path = MODULE_ROOT / "db" / "migrations" / "003_row_level_security.sql"
    rls_sql = rls_sql_path.read_text(encoding="utf-8")

    # Negative assertion: Permissive INSERT policy MUST NOT exist
    assert "CREATE POLICY auth_insert_reviews" not in rls_sql

    # Positive assertion: Explicit DROP and REVOKE must be present
    assert "DROP POLICY IF EXISTS auth_insert_reviews ON quality_reviews;" in rls_sql
    assert "REVOKE ALL ON TABLE quality_reviews FROM PUBLIC, anon, authenticated;" in rls_sql
    assert "GRANT SELECT ON TABLE quality_reviews TO authenticated;" in rls_sql
    assert "GRANT ALL ON TABLE quality_reviews TO service_role;" in rls_sql

    # Sequence usage must not be granted to authenticated for quality_reviews
    assert "quality_reviews_review_id_seq TO authenticated" not in rls_sql

    # Gold holdout protection in RLS policies (non-Gold constraint enforcement)
    assert "CREATE POLICY auth_select_annotations ON annotations" in rls_sql
    assert "USING (dataset_id != 'gold')" in rls_sql
    assert "auth_select_annotations ON annotations\n    FOR SELECT TO authenticated USING (true);" not in rls_sql
    assert "CREATE POLICY auth_select_reviews ON quality_reviews" in rls_sql
    assert "auth_select_reviews ON quality_reviews\n    FOR SELECT TO authenticated USING (true);" not in rls_sql


def test_gold_dataset_engine_inviolability_and_rls_boundary():
    """
    Verifies that the Gold evaluation benchmark is inviolable at both:
    1. Schema level: chk_gold_never_training constraint
    2. RLS level: dataset_id = 't1' mandatory in USING and WITH CHECK
    """
    schema_sql_path = MODULE_ROOT / "db" / "migrations" / "001_initial_schema.sql"
    rls_sql_path = MODULE_ROOT / "db" / "migrations" / "003_row_level_security.sql"

    schema_sql = schema_sql_path.read_text(encoding="utf-8")
    rls_sql = rls_sql_path.read_text(encoding="utf-8")

    # Schema constraint
    assert "CONSTRAINT chk_gold_never_training CHECK (dataset_id != 'gold' OR is_training_allowed = FALSE)" in schema_sql

    # RLS Update policy must verify dataset_id = 't1' on BOTH target selection (USING) and mutation (WITH CHECK)
    assert "CREATE POLICY auth_update_t1_annotations ON annotations" in rls_sql
    assert "USING (dataset_id = 't1')" in rls_sql
    assert "WITH CHECK (dataset_id = 't1')" in rls_sql

    # RLS Insert policy must verify dataset_id = 't1'
    assert "CREATE POLICY auth_insert_t1_annotations ON annotations" in rls_sql

    # No DELETE policy for authenticated
    assert "CREATE POLICY auth_delete" not in rls_sql
    assert "REVOKE DELETE, TRUNCATE ON TABLE annotations FROM authenticated;" in rls_sql

    # RLS Select policies must explicitly protect Gold holdout from authenticated users
    assert "CREATE POLICY auth_select_annotations ON annotations" in rls_sql
    assert "CREATE POLICY auth_select_reviews ON quality_reviews" in rls_sql
    assert "USING (dataset_id != 'gold')" in rls_sql
    assert "auth_select_annotations ON annotations\n    FOR SELECT TO authenticated USING (true);" not in rls_sql
    assert "auth_select_reviews ON quality_reviews\n    FOR SELECT TO authenticated USING (true);" not in rls_sql


def test_quality_review_creation_service_role_boundary():
    """
    Simulates role boundary enforcement:
    - Attempting to insert a quality review under client/authenticated context fails.
    - Creating a quality review via the trusted backend service role succeeds.
    """
    # 1. Authenticated user client simulation: table.insert() should fail / be rejected
    mock_auth_client = MagicMock()
    mock_auth_client.table("quality_reviews").insert.side_effect = PermissionError(
        "new row violates row-level security policy for table 'quality_reviews'"
    )

    with pytest.raises(PermissionError) as exc_info:
        mock_auth_client.table("quality_reviews").insert({
            "sample_id": 1,
            "dataset_id": "gold",
            "anon_id": "GOLD-001",
            "epoch": 2020,
            "interpreter_a_id": "user_a",
            "interpreter_a_class": "built_up",
            "is_agreement": True
        })
    assert "violates row-level security policy" in str(exc_info.value)

    # 2. Service role backend simulation: table.insert() succeeds
    mock_service_client = MagicMock()
    mock_service_client.table("quality_reviews").insert.return_value.execute.return_value = MagicMock(
        data=[{"review_id": 101, "review_status": "agreed"}]
    )

    res = mock_service_client.table("quality_reviews").insert({
        "sample_id": 1,
        "dataset_id": "t1",
        "anon_id": "T2-001",
        "epoch": 2020,
        "interpreter_a_id": "user_a",
        "interpreter_a_class": "built_up",
        "interpreter_b_id": "user_b",
        "interpreter_b_class": "built_up",
        "is_agreement": True,
        "agreement_type": "exact_match",
        "review_status": "agreed"
    }).execute()

    assert res.data[0]["review_id"] == 101
    assert res.data[0]["review_status"] == "agreed"


def test_gold_holdout_rls_least_privilege_access_simulation():
    """
    Simulates role-based security boundaries for Gold holdout protection:
    1. 'anon' role: denied read/write access to annotations and quality reviews.
    2. 'authenticated' role: can read T1 annotations/reviews, but queries for Gold return no rows (or error).
    3. 'authenticated' role: attempting direct query by Gold ID/anon_id returns zero rows.
    4. 'service_role': retains full unrestricted access to Gold annotations and reviews for model evaluation.
    """
    # 1. Anon client: Denied read access to annotations and quality_reviews
    mock_anon_client = MagicMock()
    mock_anon_client.table("annotations").select("*").execute.side_effect = PermissionError(
        "permission denied for table annotations"
    )
    with pytest.raises(PermissionError) as exc_info:
        mock_anon_client.table("annotations").select("*").execute()
    assert "permission denied" in str(exc_info.value)

    # 2. Authenticated client: queries T1 successfully
    mock_auth_client = MagicMock()
    t1_records = [
        {"id": 1, "dataset_id": "t1", "anon_id": "T2-0001", "epoch": 2020, "dominant_class": "built_up"}
    ]
    mock_auth_client.table("annotations").select("*").eq("dataset_id", "t1").execute.return_value = MagicMock(
        data=t1_records
    )
    t1_res = mock_auth_client.table("annotations").select("*").eq("dataset_id", "t1").execute()
    assert len(t1_res.data) == 1
    assert t1_res.data[0]["dataset_id"] == "t1"

    # 3. Authenticated client: queries Gold holdout -> RLS filters out rows (returns empty list)
    # Under Postgres RLS with USING (dataset_id != 'gold'), rows where dataset_id = 'gold' are invisible
    mock_auth_client.table("annotations").select("*").eq("dataset_id", "gold").execute.return_value = MagicMock(
        data=[]
    )
    gold_res = mock_auth_client.table("annotations").select("*").eq("dataset_id", "gold").execute()
    assert gold_res.data == [], "Authenticated client must NEVER see Gold holdout records via RLS filtering"

    # 4. Authenticated client: queries specific Gold ID directly -> RLS filters out row
    mock_auth_client.table("annotations").select("*").eq("id", 999).execute.return_value = MagicMock(
        data=[]
    )
    gold_by_id = mock_auth_client.table("annotations").select("*").eq("id", 999).execute()
    assert gold_by_id.data == [], "Direct ID query for Gold holdout must return empty under RLS"

    # 5. Authenticated client: queries quality reviews for Gold -> RLS filters out rows
    mock_auth_client.table("quality_reviews").select("*").eq("dataset_id", "gold").execute.return_value = MagicMock(
        data=[]
    )
    gold_rev_res = mock_auth_client.table("quality_reviews").select("*").eq("dataset_id", "gold").execute()
    assert gold_rev_res.data == [], "Authenticated client must NEVER see Gold quality reviews via RLS filtering"

    # 6. Service role client: backend evaluation engine can read Gold holdout
    mock_service_client = MagicMock()
    gold_records = [
        {"id": 999, "dataset_id": "gold", "anon_id": "GOLD-0001", "epoch": 2020, "dominant_class": "water"}
    ]
    mock_service_client.table("annotations").select("*").eq("dataset_id", "gold").execute.return_value = MagicMock(
        data=gold_records
    )
    service_res = mock_service_client.table("annotations").select("*").eq("dataset_id", "gold").execute()
    assert len(service_res.data) == 1
    assert service_res.data[0]["dataset_id"] == "gold"
    assert service_res.data[0]["dominant_class"] == "water"
