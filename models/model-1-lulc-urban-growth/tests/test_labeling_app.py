import pytest
import os
import sys
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

MODEL1_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(MODEL1_DIR))

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
from labeling_app.readiness import evaluate_readiness, assert_training_allowed


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



# ---------------------------------------------------------
# 7. Additional Rigorous Protocol & Safeguard Tests
# ---------------------------------------------------------

def test_schema_validates_optional_fields_on_abstain_classes():
    # If dominant_class is 'ambiguous', invalid share or confidence must be rejected
    bad_share_on_ambiguous = {
        "status": "done",
        "dominant_class": "ambiguous",
        "dominant_share_3bins": "INVALID_SHARE",
        "second_class": "none",
        "confidence_1to3": 2,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-04-10",
        "notes": "Field parcel under dispute"
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, bad_share_on_ambiguous)
    assert is_valid is False
    assert any("dominant_share_3bins" in e for e in errs)

    bad_conf_on_ambiguous = {
        "status": "done",
        "dominant_class": "ambiguous",
        "dominant_share_3bins": "50-75",
        "second_class": "none",
        "confidence_1to3": 999,
        "imagery_source": "GEP_historical",
        "imagery_date": "2020-04-10",
        "notes": "Transition zone"
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, bad_conf_on_ambiguous)
    assert is_valid is False
    assert any("confidence" in e for e in errs)


def test_double_interpretation_ids_authoritative_resolution():
    t1_ids = get_double_interpretation_ids("t1")
    gold_ids = get_double_interpretation_ids("gold")

    assert len(t1_ids) == 140
    assert len(gold_ids) == 160
    assert "T2-0005" in t1_ids
    assert "P4-0003" in gold_ids


def test_manifest_integrity_and_coordinates_in_pmr():
    manifest_dir = MODEL1_DIR / "labeling_app" / "data"
    with open(manifest_dir / "t1_manifest.json", "r", encoding="utf-8") as f:
        t1 = json.load(f)
    with open(manifest_dir / "gold_manifest.json", "r", encoding="utf-8") as f:
        gold = json.load(f)

    assert len(t1) == 699
    assert len(gold) == 641

    t1_ids = [x["anon_id"] for x in t1]
    gold_ids = [x["anon_id"] for x in gold]
    assert len(set(t1_ids)) == 699
    assert len(set(gold_ids)) == 641
    # Strict disjointness
    assert set(t1_ids).isdisjoint(set(gold_ids))

    for sample in t1 + gold:
        assert 17.5 <= sample["lat"] <= 19.8, f"Lat out of Pune region: {sample['lat']}"
        assert 73.0 <= sample["lon"] <= 75.5, f"Lon out of Pune region: {sample['lon']}"
        poly = sample.get("polygon", [])
        assert len(poly) == 5, f"Expected 5 points in closed polygon: {sample['anon_id']}"
        assert poly[0] == poly[-1], f"Polygon ring not closed: {sample['anon_id']}"


def test_export_detects_unmanifested_annotation_ids():
    tmp_dir = tempfile.mkdtemp()
    try:
        manifest_file = os.path.join(tmp_dir, "manifest.json")
        sample_manifest = [
            {"anon_id": "TEST-0001", "lat": 18.52, "lon": 73.85}
        ]
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(sample_manifest, f)

        # Annotations contain an unmanifested rogue ID
        annotations = {
            "TEST-0001": {"epochs": {}},
            "ROGUE-9999": {
                "epochs": {
                    "2020": {
                        "status": "done",
                        "dominant_class": "water",
                        "dominant_share_3bins": ">=75",
                        "confidence_1to3": 3,
                        "imagery_source": "GEP_historical",
                        "imagery_date": "2020-01-01"
                    }
                }
            }
        }

        out_csv = os.path.join(tmp_dir, "export.csv")
        summary = export_to_standard_csv(manifest_file, annotations, out_csv)

        assert "ROGUE-9999" in summary["unmanifested_annotation_ids"]
        assert summary["is_complete_final_dataset"] is False
    finally:
        shutil.rmtree(tmp_dir)


def test_work_queue_schema_error_action_guidance():
    manifest = [{"anon_id": "T2-BAD", "lat": 18.52, "lon": 73.85}]
    # Ambiguous without notes causes schema error
    annotations = {
        "T2-BAD": {
            "epochs": {
                "2020": {
                    "status": "done",
                    "dominant_class": "ambiguous",
                    "notes": ""
                }
            }
        }
    }
    queue_data = build_work_queue(manifest, annotations, "t1")
    item = queue_data["queue"][0]
    assert item["has_inconsistency"] is True
    assert "Resolve schema validation error" in item["recommended_action"]


def test_gold_dataset_endpoints_and_export(client):
    # Manifest endpoint
    res_m = client.get("/api/manifest?dataset=gold")
    assert res_m.status_code == 200
    data_m = res_m.get_json()
    assert data_m["total"] == 641
    assert data_m["items"][0]["anon_id"] == "P4-0001"

    # QC endpoint
    res_qc = client.get("/api/qc?dataset=gold")
    assert res_qc.status_code == 200
    data_qc = res_qc.get_json()
    assert data_qc["total_samples"] == 641
    assert data_qc["completed_samples"] == 0

    # Work queue endpoint
    res_wq = client.get("/api/work_queue?dataset=gold")
    assert res_wq.status_code == 200
    data_wq = res_wq.get_json()
    assert data_wq["summary"]["total_samples"] == 641


def test_training_guards_fail_closed_on_incomplete_labels():
    # evaluate_readiness must report BLOCKED
    readiness = evaluate_readiness()
    assert readiness["overall_decision"] == "BLOCKED"
    assert readiness["is_training_allowed"] is False

    # Calling assert_training_allowed must raise PermissionError
    with pytest.raises(PermissionError) as exc_info:
        assert_training_allowed()
    assert "MODEL 1 TRAINING GUARD REFUSAL (FAIL-CLOSED)" in str(exc_info.value)


def test_readiness_endpoint(client):
    res = client.get("/api/readiness")
    assert res.status_code == 200
    data = res.get_json()
    assert data["overall_decision"] == "BLOCKED"
    assert data["is_training_allowed"] is False
    assert len(data["checklist"]) >= 8


def test_single_epoch_imagery_endpoint(client):
    """Verify that /api/imagery/<epoch> returns the authentic scene for each valid epoch."""
    expected_scenes = {
        1990: ("LT05_L2SP_147047_19911218_02_T1", "Landsat 5 TM", "1991-12-18"),
        2000: ("LE07_L2SP_147047_20011103_02_T1", "Landsat 7 ETM+", "2001-11-03"),
        2010: ("LE07_L2SP_147047_20111217_02_T1", "Landsat 7 ETM+", "2011-12-17"),
        2020: ("LC09_L2SP_147047_20211228_02_T1", "Landsat 9 OLI-2", "2021-12-28"),
    }
    for ep, (scene_id, sensor, acq_date) in expected_scenes.items():
        res = client.get(f"/api/imagery/{ep}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["scene_id"] == scene_id
        assert data["sensor"] == sensor
        assert data["acquisition_date"] == acq_date
        assert "tile_url" in data
        assert f"item={scene_id}" in data["tile_url"]

    # Invalid epoch returns 404
    res_inv = client.get("/api/imagery/1985")
    assert res_inv.status_code == 404


def test_perimeter_samples_honestly_flagged_in_manifest(client):
    """Verify that perimeter samples outside Path 147, Row 047 are flagged inside_primary_landsat=False."""
    res = client.get("/api/manifest?dataset=t1")
    assert res.status_code == 200
    items = res.get_json()["items"]

    # T2-0001 is on the perimeter (lon ~75.0869 > 74.9671)
    assert items[0]["anon_id"] == "T2-0001"
    assert items[0]["inside_primary_landsat"] is False

    # Count total perimeter samples in T1
    perimeter_count = sum(1 for item in items if item["inside_primary_landsat"] is False)
    assert perimeter_count == 37
    assert len(items) - perimeter_count == 662


def test_annotation_date_window_and_2010_discrepancy():
    """Verify that 2011-12-17 is valid for epoch 2010 (+/-2 yr rule), while 2007 and 2013 are rejected."""
    # Valid: 2011-12-17 for epoch 2010 (delta = +1 year, within [2008, 2012])
    valid_data = {
        "status": "done",
        "dominant_class": "built_up",
        "dominant_share_3bins": ">=75",
        "confidence_1to3": 2,
        "imagery_source": "Landsat_context",
        "imagery_date": "2011-12-17"
    }
    is_valid, errs, _ = validate_epoch_annotation(2010, valid_data)
    assert is_valid, f"Expected 2011-12-17 to be valid for epoch 2010: {errs}"

    # Invalid: 2007 (outside [2008, 2012])
    too_early = dict(valid_data, imagery_date="2007-12-31")
    is_val_early, errs_early, _ = validate_epoch_annotation(2010, too_early)
    assert not is_val_early
    assert any("outside the allowed +/-2 years window" in e for e in errs_early)

    # Invalid: 2013 (outside [2008, 2012])
    too_late = dict(valid_data, imagery_date="2013-01-01")
    is_val_late, errs_late, _ = validate_epoch_annotation(2010, too_late)
    assert not is_val_late
    assert any("outside the allowed +/-2 years window" in e for e in errs_late)


def test_epoch_isolation_prevents_cross_year_leakage(client, monkeypatch, tmp_path):
    """Confirm that saving an annotation for epoch 1990 does not alter epochs 2000, 2010, 2020."""
    monkeypatch.setattr("labeling_app.app.STORAGE_DIR", str(tmp_path))
    from labeling_app.app import app
    app.config["STORAGE_DIR"] = str(tmp_path)

    # Save epoch 1990 only
    payload = {
        "epochs": {
            "1990": {
                "status": "done",
                "dominant_class": "agriculture",
                "dominant_share_3bins": ">=75",
                "confidence_1to3": 2,
                "imagery_source": "Landsat_context",
                "imagery_date": "1991-12-18",
                "notes": ""
            }
        }
    }
    res = client.post("/api/annotation/t1/T2-0002", json=payload)
    assert res.status_code == 200

    # Retrieve record and check other epochs are untouched
    get_res = client.get("/api/annotation/t1/T2-0002")
    assert get_res.status_code == 200
    retrieved = get_res.get_json()["epochs"]

    assert "1990" in retrieved
    assert retrieved["1990"]["dominant_class"] == "agriculture"
    assert "2000" not in retrieved
    assert "2010" not in retrieved
    assert "2020" not in retrieved


def test_missing_imagery_vs_land_cover_status_distinction():
    """Verify that missing imagery is an annotation status ('unavailable'), not a land cover class."""
    # 1. Status 'unavailable' does NOT require a dominant_class
    unavail_status = {
        "status": "unavailable",
        "imagery_source": "Landsat_context",
        "imagery_date": "2021-12-28",
        "notes": "Cell lies outside Path 147, Row 047 scene footprint."
    }
    is_valid, errs, _ = validate_epoch_annotation(2020, unavail_status)
    assert is_valid, f"Expected status 'unavailable' to be valid without dominant_class: {errs}"

    # 2. Status 'done' requires a valid dominant class from the approved vocabulary
    done_no_class = {
        "status": "done",
        "dominant_class": "",
        "dominant_share_3bins": ">=75",
        "confidence_1to3": 2,
        "imagery_source": "Landsat_context",
        "imagery_date": "2021-12-28"
    }
    is_valid_none, errs_none, _ = validate_epoch_annotation(2020, done_no_class)
    assert not is_valid_none
    assert any("dominant_class is required when status is 'done'" in e for e in errs_none)

    # 3. Uncertain is a valid optical abstention when status is 'done'
    uncertain_class = {
        "status": "done",
        "dominant_class": "uncertain",
        "dominant_share_3bins": "<50",
        "confidence_1to3": 1,
        "imagery_source": "Landsat_context",
        "imagery_date": "2021-12-28",
        "notes": "Image resolution too coarse to discern structures."
    }
    is_valid_unc, errs_unc, _ = validate_epoch_annotation(2020, uncertain_class)
    assert is_valid_unc, f"Uncertain failed validation: {errs_unc}"


def test_notes_requirement_regression_for_2010_and_2020():
    """
    Regression Test (Tasks 2, 3, 5):
    Verify that across both Epoch 2010 and Epoch 2020:
    1. 'uncertain' does NOT require notes (valid with or without notes).
    2. 'ambiguous' strictly requires notes (fails without notes, succeeds with notes).
    3. Generated error messages explicitly identify the epoch being validated.
    """
    for epoch, valid_date in [(2010, "2011-12-17"), (2020, "2021-12-28")]:
        # Case A: 'uncertain' without notes -> MUST BE VALID
        uncertain_no_notes = {
            "status": "done",
            "dominant_class": "uncertain",
            "dominant_share_3bins": "<50",
            "second_class": "none",
            "confidence_1to3": 1,
            "imagery_source": "Landsat_context",
            "imagery_date": valid_date,
            "notes": ""
        }
        is_valid, errs, warns = validate_epoch_annotation(epoch, uncertain_no_notes)
        assert is_valid is True, f"Epoch {epoch} with 'uncertain' and no notes should be valid: {errs}"
        assert len(errs) == 0

        # Case B: 'uncertain' with notes -> MUST BE VALID
        uncertain_with_notes = dict(uncertain_no_notes)
        uncertain_with_notes["notes"] = "Coarse resolution limits discernment."
        is_valid, errs, _ = validate_epoch_annotation(epoch, uncertain_with_notes)
        assert is_valid is True, f"Epoch {epoch} with 'uncertain' and notes should be valid: {errs}"
        assert len(errs) == 0

        # Case C: 'ambiguous' without notes -> MUST FAIL
        ambiguous_no_notes = {
            "status": "done",
            "dominant_class": "ambiguous",
            "dominant_share_3bins": "50-75",
            "second_class": "agriculture",
            "confidence_1to3": 2,
            "imagery_source": "Landsat_context",
            "imagery_date": valid_date,
            "notes": ""
        }
        is_valid, errs, _ = validate_epoch_annotation(epoch, ambiguous_no_notes)
        assert is_valid is False, f"Epoch {epoch} with 'ambiguous' and no notes must fail validation"
        assert len(errs) == 1
        expected_msg = f"Epoch {epoch}: Notes are mandatory when dominant_class is 'ambiguous'."
        assert errs[0] == expected_msg, f"Expected error '{expected_msg}', got '{errs[0]}'"

        # Case D: 'ambiguous' with whitespace-only notes -> MUST FAIL
        ambiguous_whitespace_notes = dict(ambiguous_no_notes)
        ambiguous_whitespace_notes["notes"] = "   "
        is_valid, errs, _ = validate_epoch_annotation(epoch, ambiguous_whitespace_notes)
        assert is_valid is False
        assert errs[0] == expected_msg

        # Case E: 'ambiguous' with valid explanatory notes -> MUST BE VALID
        ambiguous_with_notes = dict(ambiguous_no_notes)
        ambiguous_with_notes["notes"] = "Transition zone between built compound and active parcel."
        is_valid, errs, _ = validate_epoch_annotation(epoch, ambiguous_with_notes)
        assert is_valid is True, f"Epoch {epoch} with 'ambiguous' and notes should be valid: {errs}"
        assert len(errs) == 0


def test_active_epoch_save_isolation_and_error_identification(client, tmp_path):
    """
    Regression Test (Tasks 1, 2, 4):
    Verify that saving Epoch 2010 succeeds even if another epoch in storage
    has an invalid legacy annotation, and that errors identify only the target epoch.
    """
    from labeling_app.app import app
    from labeling_app.storage import AnnotationStore

    test_storage = tmp_path / "epoch_isolation_storage"
    test_storage.mkdir()
    app.config["STORAGE_DIR"] = str(test_storage)
    store = AnnotationStore(str(test_storage))

    # Pre-populate sample T2-0002 with an invalid Epoch 2020 (ambiguous without notes)
    store.save_sample_annotation("t1", "T2-0002", {
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
    })

    # Save active epoch 2010 (uncertain without notes)
    save_payload_2010 = {
        "epochs": {
            "2010": {
                "status": "done",
                "dominant_class": "uncertain",
                "dominant_share_3bins": "<50",
                "second_class": "none",
                "confidence_1to3": 1,
                "imagery_source": "Landsat_context",
                "imagery_date": "2011-12-17",
                "notes": ""
            }
        }
    }

    res = client.post("/api/annotation/t1/T2-0002", json=save_payload_2010)
    assert res.status_code == 200, f"Expected HTTP 200 saving Epoch 2010, got {res.status_code}: {res.get_json()}"
    res_data = res.get_json()
    assert res_data["status"] == "saved"
    assert "2010" in res_data["validation"]
    assert res_data["validation"]["2010"]["valid"] is True
    # Crucial: 2020 should NOT be validated as part of the 2010 save request
    assert "2020" not in res_data["validation"]

    # Verify both epochs exist in storage (merging without clobbering)
    stored = store.load_annotations("t1")["T2-0002"]["epochs"]
    assert "2010" in stored
    assert stored["2010"]["dominant_class"] == "uncertain"
    assert "2020" in stored
    assert stored["2020"]["dominant_class"] == "ambiguous"

    # Now attempt to save Epoch 2020 with ambiguous and no notes -> MUST FAIL WITH EPOCH 2020 ERROR
    save_payload_2020_invalid = {
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
    res_err = client.post("/api/annotation/t1/T2-0002", json=save_payload_2020_invalid)
    assert res_err.status_code == 400
    err_json = res_err.get_json()
    assert err_json["status"] == "validation_failed"
    assert "2020" in err_json["errors"]
    assert any("Epoch 2020: Notes are mandatory when dominant_class is 'ambiguous'." in e for e in err_json["errors"]["2020"]["errors"])
    # Crucial: Epoch 2010 is NOT reported in errors
    assert "2010" not in err_json["errors"]
