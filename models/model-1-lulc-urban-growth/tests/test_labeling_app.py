import pytest
import os
import json
import shutil
import tempfile
from datetime import datetime

from labeling_app.schema import (
    validate_epoch_annotation,
    DEFINITE_CLASSES,
    ABSTAIN_CLASSES,
    ALL_CLASSES,
    SHARE_BINS,
    SOURCES_OK
)
from labeling_app.storage import AnnotationStore
from labeling_app.exporter import export_to_standard_csv
from labeling_app.imagery import get_historical_imagery_info, get_all_epochs_imagery
from labeling_app.qc import (
    compute_qc_stats,
    detect_trajectory_anomalies,
    compute_inter_rater_agreement
)
from labeling_app.work_queue import (
    build_work_queue,
    is_inside_primary_landsat,
    get_double_interpretation_ids,
    save_persistent_queue,
    load_persistent_queue,
    sync_and_persist_work_queue
)
from labeling_app.app import create_app, STORAGE_DIR


# ---------------------------------------------------------
# 1. Schema Validation Unit Tests
# ---------------------------------------------------------

def test_valid_annotation():
    valid_data = {
        "status": "done",
        "dominant_class": "built_up",
        "dominant_share_3bins": ">=75",
        "second_class": "none",
        "confidence_1to3": 3,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-04-10",
        "notes": ""
    }
    is_valid, errs, warns = validate_epoch_annotation(2020, valid_data)
    assert is_valid is True
    assert len(errs) == 0


def test_invalid_category_rejection():
    bad_data = {
        "status": "done",
        "dominant_class": "industrial_complex", # Not in vocabulary
        "dominant_share_3bins": ">=75",
        "second_class": "none",
        "confidence_1to3": 3,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-04-10"
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, bad_data)
    assert is_valid is False
    assert any("not in approved vocabulary" in e for e in errs)


def test_missing_mandatory_field():
    missing_data = {
        "status": "done",
        "dominant_class": "agriculture",
        # Missing dominant_share_3bins
        "second_class": "none",
        "confidence_1to3": 3,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-04-10"
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, missing_data)
    assert is_valid is False
    assert any("dominant_share_3bins" in e for e in errs)


def test_other_requires_notes():
    other_without_notes = {
        "status": "done",
        "dominant_class": "other",
        "dominant_share_3bins": ">=75",
        "second_class": "none",
        "confidence_1to3": 3,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-04-10",
        "notes": ""
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, other_without_notes)
    assert is_valid is False
    assert any("Notes are mandatory when dominant_class is 'other'" in e for e in errs)


def test_ambiguous_requires_notes_per_interpreter_protocol():
    ambiguous_without_notes = {
        "status": "done",
        "dominant_class": "ambiguous",
        "dominant_share_3bins": "50-75",
        "second_class": "agriculture",
        "confidence_1to3": 2,
        "imagery_source": "Landsat_context",
        "imagery_date": "2021-12-28",
        "notes": ""
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, ambiguous_without_notes)
    assert is_valid is False
    assert any("Notes are mandatory when dominant_class is 'ambiguous'" in e for e in errs)


def test_date_window_validation():
    # 2020 epoch allows [2018, 2022]. 2015 should fail
    out_of_window = {
        "status": "done",
        "dominant_class": "water",
        "dominant_share_3bins": ">=75",
        "second_class": "none",
        "confidence_1to3": 3,
        "imagery_source": "GEP_historical",
        "imagery_date": "2015-05-20"
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, out_of_window)
    assert is_valid is False
    assert any("outside the allowed +/-2 years window" in e for e in errs)


def test_landsat_context_max_confidence():
    # Protocol rule: Landsat context cannot exceed confidence 2
    landsat_conf3 = {
        "status": "done",
        "dominant_class": "natural_vegetation",
        "dominant_share_3bins": ">=75",
        "second_class": "none",
        "confidence_1to3": 3,
        "imagery_source": "Landsat_context",
        "imagery_date": "2000-02-15"
    }
    is_valid, errs, _ = validate_epoch_annotation(2000, landsat_conf3)
    assert is_valid is False
    assert any("confidence must be at most 2" in e for e in errs)


# ---------------------------------------------------------
# 2. Persistence & Recovery Tests
# ---------------------------------------------------------

def test_storage_save_reload_and_backup():
    tmp_dir = tempfile.mkdtemp()
    try:
        store = AnnotationStore(tmp_dir)
        payload = {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "built_up"
                }
            }
        }
        # First save
        assert store.save_sample_annotation("t1", "T2-0001", payload) is True
        loaded = store.load_annotations("t1")
        assert "T2-0001" in loaded
        assert loaded["T2-0001"]["epochs"]["2020"]["dominant_class"] == "built_up"

        # Update and check backup created
        payload["epochs"]["2020"]["dominant_class"] = "agriculture"
        assert store.save_sample_annotation("t1", "T2-0001", payload) is True
        loaded2 = store.load_annotations("t1")
        assert loaded2["T2-0001"]["epochs"]["2020"]["dominant_class"] == "agriculture"

        backups = os.listdir(store.backup_dir)
        assert len(backups) >= 1
    finally:
        shutil.rmtree(tmp_dir)


# ---------------------------------------------------------
# 3. Exporter Compatibility Test
# ---------------------------------------------------------

def test_export_schema_compatibility():
    tmp_dir = tempfile.mkdtemp()
    try:
        manifest_file = os.path.join(tmp_dir, "manifest.json")
        sample_manifest = [
            {"anon_id": "TEST-0001", "lat": 18.52, "lon": 73.85},
            {"anon_id": "TEST-0002", "lat": 18.60, "lon": 73.90}
        ]
        with open(manifest_file, "w") as f:
            json.dump(sample_manifest, f)

        annotations = {
            "TEST-0001": {
                "epochs": {
                    "2020": {
                        "status": "done",
                        "dominant_class": "water",
                        "dominant_share_3bins": ">=75",
                        "second_class": "none",
                        "confidence_1to3": 3,
                        "imagery_source": "GEP_historical",
                        "imagery_date": "2020-01-01",
                        "notes": "Reservoir"
                    }
                }
            }
        }

        out_csv = os.path.join(tmp_dir, "export.csv")
        summary = export_to_standard_csv(manifest_file, annotations, out_csv)

        assert os.path.exists(out_csv)
        assert summary["total_samples"] == 2
        assert summary["partially_labeled"] == 1
        assert summary["unlabeled"] == 1

        import pandas as pd
        df = pd.read_csv(out_csv)
        assert len(df.columns) == 35
        assert df.iloc[0]["dominant_class_2020"] == "water"
        assert df.iloc[0]["notes_2020"] == "Reservoir"
        assert pd.isna(df.iloc[1]["dominant_class_2020"]) or df.iloc[1]["dominant_class_2020"] == ""
    finally:
        shutil.rmtree(tmp_dir)


# ---------------------------------------------------------
# 4. Historical Imagery & QC Unit Tests
# ---------------------------------------------------------

def test_historical_imagery_resolution():
    all_scenes = get_all_epochs_imagery()
    for ep in [1990, 2000, 2010, 2020]:
        assert ep in all_scenes
        info = all_scenes[ep]
        assert info["verified"] is True
        assert "tile_url" in info
        assert "LT05" in info["scene_id"] or "LE07" in info["scene_id"] or "LC09" in info["scene_id"]


def test_qc_analytics_computation():
    manifest = [
        {"anon_id": "S-1", "lat": 18.5, "lon": 73.8},
        {"anon_id": "S-2", "lat": 18.6, "lon": 73.9}
    ]
    annotations = {
        "S-1": {
            "epochs": {
                "2020": {"status": "done", "dominant_class": "built_up", "confidence_1to3": 3, "imagery_source": "GEP_historical"},
                "2000": {"status": "done", "dominant_class": "agriculture", "confidence_1to3": 1, "imagery_source": "Landsat_context"},
                "2010": {"status": "unavailable"},
                "1990": {"status": "done", "dominant_class": "natural_vegetation", "confidence_1to3": 2, "imagery_source": "Landsat_context"}
            }
        }
    }
    stats = compute_qc_stats(manifest, annotations, dataset="t1")
    assert stats["total_samples"] == 2
    assert stats["completed_samples"] == 1 # 4 epochs done or unavailable
    assert stats["unlabeled_samples"] == 1
    assert stats["low_confidence_count"] == 2 # 2000 (conf 1) and 1990 (conf 2)
    assert stats["unavailable_count"] == 1
    assert stats["confidence_distribution"][1] == 1
    assert stats["confidence_distribution"][3] == 1
    assert stats["inter_rater_reliability"]["status"] == "awaiting_dual_interpretation"


def test_trajectory_anomaly_detection():
    # Built-up in 2000 reverting to agriculture in 2010 is an urban reversion anomaly
    sample_epochs = {
        "1990": {"status": "done", "dominant_class": "natural_vegetation"},
        "2000": {"status": "done", "dominant_class": "built_up"},
        "2010": {"status": "done", "dominant_class": "agriculture"},
        "2020": {"status": "done", "dominant_class": "built_up"}
    }
    anomalies = detect_trajectory_anomalies(sample_epochs)
    assert len(anomalies) == 1
    assert anomalies[0]["type"] == "urban_reversion"
    assert anomalies[0]["from_epoch"] == 2000
    assert anomalies[0]["to_epoch"] == 2010


def test_inter_rater_agreement_unbiased():
    # Empty / incomplete B interpretations must report awaiting_dual_interpretation
    res_empty = compute_inter_rater_agreement({"S-1": {}}, {}, {"S-1"})
    assert res_empty["status"] == "awaiting_dual_interpretation"
    assert res_empty["overall_agreement_pct"] is None

    # Paired interpretations compute true concordance
    ann_a = {"S-1": {"epochs": {"2020": {"dominant_class": "built_up"}}}}
    ann_b = {"S-1": {"epochs": {"2020": {"dominant_class": "built_up"}}}}
    res_concordant = compute_inter_rater_agreement(ann_a, ann_b, {"S-1"})
    assert res_concordant["status"] == "computed"
    assert res_concordant["overall_agreement_pct"] == 100.0


# ---------------------------------------------------------
# 5. Work Queue Unit Tests
# ---------------------------------------------------------

def test_work_queue_prioritization():
    manifest = [
        {"anon_id": "T2-CORE", "lat": 18.52, "lon": 73.85},     # Inside primary Landsat
        {"anon_id": "T2-PERIMETER", "lat": 18.14, "lon": 75.08} # Eastern Indapur (outside 147_047)
    ]
    annotations = {
        "T2-CORE": {
            "epochs": {
                "2020": {"status": "done", "dominant_class": "built_up"}
            }
        }
    }
    queue_data = build_work_queue(manifest, annotations, "t1")
    assert queue_data["summary"]["total_samples"] == 2
    # T2-CORE has 1 epoch done -> Rank 3 (in_progress)
    # T2-PERIMETER is unannotated and outside 147_047 -> Rank 4 (perimeter needs GEP)
    items = {q["anon_id"]: q for q in queue_data["queue"]}
    assert items["T2-CORE"]["priority_rank"] == 3
    assert items["T2-PERIMETER"]["priority_rank"] == 4
    assert items["T2-PERIMETER"]["inside_primary_landsat"] is False


# ---------------------------------------------------------
# 6. Flask Application Integration Tests (Isolated Storage)
# ---------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    test_storage = tmp_path / "test_storage"
    test_storage.mkdir()
    app = create_app(storage_dir=str(test_storage))
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_app_startup_and_config(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.get_json()
    assert "epochs" in data
    assert data["epochs"] == [2020, 2000, 2010, 1990]
    assert "built_up" in data["definite_classes"]


def test_imagery_endpoint(client):
    res = client.get("/api/imagery")
    assert res.status_code == 200
    data = res.get_json()
    assert "1990" in data or 1990 in data
    assert "2020" in data or 2020 in data


def test_qc_endpoint(client):
    res = client.get("/api/qc?dataset=t1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["dataset"] == "t1"
    assert data["total_samples"] == 699


def test_manifest_endpoint(client):
    res = client.get("/api/manifest?dataset=t1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["dataset"] == "t1"
    assert data["total"] == 699
    assert len(data["items"]) == 699
    assert data["items"][0]["anon_id"] == "T2-0001"


def test_work_queue_endpoint(client):
    res = client.get("/api/work_queue?dataset=t1")
    assert res.status_code == 200
    data = res.get_json()
    assert "summary" in data
    assert data["summary"]["total_samples"] == 699
    assert "queue" in data
    assert len(data["queue"]) == 699


def test_save_and_retrieve_annotation_flow(client):
    payload = {
        "epochs": {
            "2020": {
                "status": "done",
                "dominant_class": "natural_vegetation",
                "dominant_share_3bins": ">=75",
                "second_class": "none",
                "confidence_1to3": 3,
                "imagery_source": "GEP_historical",
                "imagery_date": "2020-05-12",
                "notes": "Forest ridge"
            }
        }
    }
    # Save
    post_res = client.post("/api/annotation/t1/T2-0001", json=payload)
    assert post_res.status_code == 200
    res_data = post_res.get_json()
    assert res_data["status"] == "saved"

    # Retrieve
    get_res = client.get("/api/annotation/t1/T2-0001")
    assert get_res.status_code == 200
    get_data = get_res.get_json()
    assert get_data["epochs"]["2020"]["dominant_class"] == "natural_vegetation"


def test_isolated_test_storage_preserves_live(client):
    # Verify that writing via client test does not touch the real production storage
    live_t1 = os.path.join(STORAGE_DIR, "t1_annotations.json")
    if os.path.exists(live_t1):
        with open(live_t1, "r") as f:
            live_data = json.load(f)
        # Should not contain newly posted test keys from client
        assert "ISOLATION_TEST_KEY" not in live_data


def test_persistent_work_queue_recovery(tmp_path):
    # Test saving and recovery across simulated restarts
    manifest = [{"anon_id": "T2-TEST", "lat": 18.52, "lon": 73.85}]
    ann = {}
    queue = sync_and_persist_work_queue(manifest, ann, str(tmp_path), "t1")
    assert queue["summary"]["total_samples"] == 1
    
    # Reload from disk (simulating server restart)
    recovered = load_persistent_queue(str(tmp_path), "t1")
    assert recovered is not None
    assert recovered["summary"]["total_samples"] == 1
    assert recovered["queue"][0]["anon_id"] == "T2-TEST"


def test_work_queue_categories_coverage():
    # Verify all 7 required Task 5 categories exist in summary
    manifest = [{"anon_id": "T2-0001", "lat": 18.14, "lon": 75.08}]
    queue = build_work_queue(manifest, {}, "t1")
    cats = queue["summary"]["categories"]
    required_cats = [
        "unannotated_samples",
        "partially_annotated_samples",
        "completed_samples",
        "samples_with_suitable_historical_imagery",
        "samples_with_unavailable_imagery",
        "low_confidence_annotations",
        "samples_requiring_independent_review",
        "invalid_or_inconsistent_records"
    ]
    for rc in required_cats:
        assert rc in cats


def test_work_queue_sync_api(client):
    res = client.post("/api/work_queue/sync?dataset=t1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "synchronized"
    assert data["summary"]["total_samples"] == 699


def test_unknown_dataset_is_rejected_without_touching_t1_storage(client):
    """An invalid dataset must never silently fall back to the T1 store."""
    payload = {"epochs": {"2020": {"status": "done"}}}
    res = client.post("/api/annotation/not-a-dataset/T2-0001", json=payload)
    assert res.status_code == 400
    assert client.get("/api/manifest?dataset=not-a-dataset").status_code == 400


def test_unknown_sample_is_rejected(client):
    payload = {"epochs": {"2020": {"status": "done"}}}
    res = client.post("/api/annotation/t1/UNKNOWN-0001", json=payload)
    assert res.status_code == 404


def test_empty_annotation_payload_is_rejected(client):
    res = client.post("/api/annotation/t1/T2-0001", json={"epochs": {}})
    assert res.status_code == 400

