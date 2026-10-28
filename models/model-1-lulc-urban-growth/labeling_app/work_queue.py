"""
Persistent Work Queue and Progress Management for Model 1 Visual Interpretation.

Fulfills Task 5 of the Research Protocol:
1. Identifies:
   - Unannotated samples
   - Partially annotated samples
   - Samples with suitable historical imagery
   - Samples with unavailable imagery
   - Low-confidence annotations
   - Samples requiring independent review
   - Invalid or inconsistent records
2. Computes progress by:
   - Dataset
   - Epoch
   - Annotation status
   - Confidence
   - Imagery availability
3. Provides persistent JSON storage in STORAGE_DIR/work_queue_<dataset>.json,
   making the work queue immediately recoverable across application restarts.
"""

import os
import json
import zipfile
import io
import time
import shutil
from datetime import datetime, timezone
import pandas as pd
from .schema import EPOCHS, CONFIDENCE_LEVELS, ALL_CLASSES, validate_epoch_annotation

# Conservative 4-epoch intersection bounding box for Landsat Path 147, Row 047
PRIMARY_LANDSAT_BBOX = {
    "min_lon": 72.82681858,
    "min_lat": 17.8301545,
    "max_lon": 74.96711309,
    "max_lat": 19.7355255
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPO_ROOT = os.path.dirname(BASE_DIR)

# Cached double interpretation IDs
_DOUBLE_INTERPRETATION_CACHE = {}

def get_double_interpretation_ids(dataset: str = "t1") -> set:
    """
    Retrieves the authoritative set of sample IDs designated for double-interpretation
    from data/double_interpretation_ids.json, existing storage, or Phase 6 Interpreter B kits.
    """
    global _DOUBLE_INTERPRETATION_CACHE
    safe_ds = "gold" if dataset == "gold" else "t1"
    if safe_ds in _DOUBLE_INTERPRETATION_CACHE:
        return _DOUBLE_INTERPRETATION_CACHE[safe_ds]

    ids = set()

    # 1. Primary source: permanent authoritative JSON reference in data directory
    json_path = os.path.join(DATA_DIR, "double_interpretation_ids.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                ids = set(data.get(safe_ds, []))
        except Exception as e:
            print(f"Warning: could not read {json_path}: {e}")

    # 2. Secondary fallback: check legacy zip kits if present
    if not ids:
        zip_name = "phase6_gold_kit_INTERPRETER_B.zip" if safe_ds == "gold" else "phase6_T1v2_kit_INTERPRETER_B.zip"
        csv_name = "gold_form_interpreter_B.csv" if safe_ds == "gold" else "T1v2_form_interpreter_B.csv"
        zip_path = os.path.join(REPO_ROOT, "phase6", "data", zip_name)

        if os.path.exists(zip_path):
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    df = pd.read_csv(io.BytesIO(zf.read(csv_name)))
                    ids = set(df["anon_id"].dropna().astype(str).tolist())
            except Exception as e:
                print(f"Warning: could not read {zip_name}: {e}")

    # 3. Tertiary fallback: inspect existing persistent work queue in storage
    if not ids:
        q_path = os.path.join(BASE_DIR, "storage", f"work_queue_{safe_ds}.json")
        if os.path.exists(q_path):
            try:
                with open(q_path, "r", encoding="utf-8") as f:
                    q_data = json.load(f)
                    ids = {q["anon_id"] for q in q_data.get("queue", []) if q.get("is_double_interpretation")}
            except Exception as e:
                print(f"Warning: could not read {q_path}: {e}")

    _DOUBLE_INTERPRETATION_CACHE[safe_ds] = ids
    return ids


def is_inside_primary_landsat(lat: float, lon: float) -> bool:
    """
    Checks if coordinates fall strictly within the 4-epoch footprint intersection
    of the primary Landsat scene (Path 147, Row 047).
    """
    return (
        PRIMARY_LANDSAT_BBOX["min_lat"] <= lat <= PRIMARY_LANDSAT_BBOX["max_lat"] and
        PRIMARY_LANDSAT_BBOX["min_lon"] <= lon <= PRIMARY_LANDSAT_BBOX["max_lon"]
    )


def detect_trajectory_anomalies(sample_epochs: dict) -> list:
    """
    Scans temporal sequence (1990 -> 2000 -> 2010 -> 2020) for improbable transitions,
    such as built-up reverting to agriculture or natural vegetation.
    """
    chrono_epochs = [1990, 2000, 2010, 2020]
    anomalies = []
    prev_class = None
    prev_epoch = None

    for ep in chrono_epochs:
        ann = sample_epochs.get(str(ep), {})
        status = ann.get("status", "")
        if status != "done":
            continue
        curr_class = ann.get("dominant_class", "")
        if not curr_class or curr_class in ["uncertain", "ambiguous", "unavailable"]:
            continue

        if prev_class == "built_up" and curr_class in ["agriculture", "natural_vegetation"]:
            anomalies.append({
                "type": "urban_reversion",
                "message": f"Potential reversion: '{prev_class}' in {prev_epoch} -> '{curr_class}' in {ep}.",
                "from_epoch": prev_epoch,
                "to_epoch": ep,
                "from_class": prev_class,
                "to_class": curr_class
            })

        prev_class = curr_class
        prev_epoch = ep

    return anomalies


def build_work_queue(manifest: list, annotations: dict, dataset: str = "t1") -> dict:
    """
    Builds the 7 required work queue categories and progress breakdowns.
    """
    double_ids = get_double_interpretation_ids(dataset)
    queue = []

    # Category sets
    category_counts = {
        "unannotated_samples": 0,
        "partially_annotated_samples": 0,
        "completed_samples": 0,
        "samples_with_suitable_historical_imagery": 0,
        "samples_with_unavailable_imagery": 0,
        "low_confidence_annotations": 0,
        "samples_requiring_independent_review": 0,
        "invalid_or_inconsistent_records": 0
    }

    # Progress tracking structures
    epoch_progress = {
        str(ep): {"done": 0, "unavailable": 0, "skipped": 0, "unlabeled": 0}
        for ep in EPOCHS
    }
    confidence_counts = {c: 0 for c in CONFIDENCE_LEVELS}
    status_counts = {"unlabeled": 0, "in_progress": 0, "completed": 0}
    imagery_availability_counts = {
        "primary_landsat_suitable": 0,
        "perimeter_needs_gep": 0,
        "unavailable_flagged": 0
    }

    priority_counts = {
        "P1_unannotated_primary_landsat": 0,
        "P2_double_interpretation_pending": 0,
        "P3_in_progress_partial": 0,
        "P4_perimeter_needs_gep": 0,
        "P5_completed_ready_for_audit": 0
    }

    for item in manifest:
        aid = item["anon_id"]
        lat = float(item["lat"])
        lon = float(item["lon"])
        
        sample_ann = annotations.get(aid, {}).get("epochs", {})
        done_epochs = []
        has_unavailable = False
        has_low_conf = False
        has_schema_error = False

        for ep in EPOCHS:
            ep_str = str(ep)
            ann = sample_ann.get(ep_str, {})
            st = ann.get("status", "")
            
            if st == "done":
                done_epochs.append(ep)
                epoch_progress[ep_str]["done"] += 1
                conf = ann.get("confidence_1to3")
                conf_int = None
                try:
                    conf_int = int(conf) if conf is not None and conf != "" else None
                except (ValueError, TypeError):
                    pass
                if conf_int in confidence_counts:
                    confidence_counts[conf_int] += 1
                if conf_int in [1, 2]:
                    has_low_conf = True

                # Schema check
                is_valid, _, _ = validate_epoch_annotation(ep, ann)
                if not is_valid:
                    has_schema_error = True

            elif st == "unavailable":
                done_epochs.append(ep)
                epoch_progress[ep_str]["unavailable"] += 1
                has_unavailable = True
            elif st == "skipped":
                epoch_progress[ep_str]["skipped"] += 1
            else:
                epoch_progress[ep_str]["unlabeled"] += 1

        inside_primary = is_inside_primary_landsat(lat, lon)
        is_double = aid in double_ids
        anomalies = detect_trajectory_anomalies(sample_ann)
        has_anomalies = len(anomalies) > 0 or has_schema_error
        remaining_epochs = [ep for ep in EPOCHS if ep not in done_epochs]

        # Classify status
        if len(done_epochs) == len(EPOCHS):
            status = "completed"
            status_counts["completed"] += 1
            category_counts["completed_samples"] += 1
            priority_rank = 5
            priority_code = "P5_completed_ready_for_audit"
            action = "All 4 epochs labeled. Ready for quality-control audit."
        elif len(done_epochs) > 0:
            status = "in_progress"
            status_counts["in_progress"] += 1
            category_counts["partially_annotated_samples"] += 1
            priority_rank = 3
            priority_code = "P3_in_progress_partial"
            action = f"Complete remaining epochs: {remaining_epochs}."
        else:
            status = "unlabeled"
            status_counts["unlabeled"] += 1
            category_counts["unannotated_samples"] += 1
            if is_double:
                priority_rank = 2
                priority_code = "P2_double_interpretation_pending"
                action = "Priority double-interpretation sample. Label independently across all 4 epochs."
            elif inside_primary:
                priority_rank = 1
                priority_code = "P1_unannotated_primary_landsat"
                action = "Unannotated sample with full in-browser Landsat Collection 2 coverage. Ready to label."
            else:
                priority_rank = 4
                priority_code = "P4_perimeter_needs_gep"
                action = "Perimeter sample (outside primary scene 147_047). Copy coords and inspect Google Earth Pro historical slider."

        if has_schema_error:
            action = f"Resolve schema validation error in saved epoch(s). {action}"
        elif len(anomalies) > 0:
            action = f"Review trajectory anomaly ({anomalies[0]['type']}). {action}"

        priority_counts[priority_code] += 1

        # Imagery classification
        if inside_primary:
            category_counts["samples_with_suitable_historical_imagery"] += 1
            imagery_availability_counts["primary_landsat_suitable"] += 1
        else:
            imagery_availability_counts["perimeter_needs_gep"] += 1

        if has_unavailable:
            category_counts["samples_with_unavailable_imagery"] += 1
            imagery_availability_counts["unavailable_flagged"] += 1

        if has_low_conf:
            category_counts["low_confidence_annotations"] += 1

        if is_double or has_anomalies:
            category_counts["samples_requiring_independent_review"] += 1

        if has_anomalies:
            category_counts["invalid_or_inconsistent_records"] += 1

        queue.append({
            "anon_id": aid,
            "lat": lat,
            "lon": lon,
            "priority_rank": priority_rank,
            "priority_code": priority_code,
            "status": status,
            "inside_primary_landsat": inside_primary,
            "is_double_interpretation": is_double,
            "completed_epochs_count": len(done_epochs),
            "completed_epochs": done_epochs,
            "remaining_epochs": remaining_epochs,
            "has_low_confidence": has_low_conf,
            "has_unavailable_imagery": has_unavailable,
            "has_inconsistency": has_anomalies,
            "anomalies": anomalies,
            "recommended_action": action
        })

    # Sort queue by priority rank (1 first), then double interpretation (True first), then anon_id
    queue.sort(key=lambda x: (x["priority_rank"], not x["is_double_interpretation"], x["anon_id"]))

    summary = {
        "dataset": dataset,
        "total_samples": len(manifest),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "categories": category_counts,
        "progress_by_status": status_counts,
        "progress_by_epoch": epoch_progress,
        "progress_by_confidence": confidence_counts,
        "progress_by_imagery_availability": imagery_availability_counts,
        "priority_breakdown": priority_counts,
        "inside_primary_landsat_count": sum(1 for q in queue if q["inside_primary_landsat"]),
        "perimeter_count": sum(1 for q in queue if not q["inside_primary_landsat"]),
        "double_interpretation_total": len(double_ids),
        "ready_for_immediate_labeling": priority_counts["P1_unannotated_primary_landsat"] + priority_counts["P2_double_interpretation_pending"],
        "in_progress": priority_counts["P3_in_progress_partial"],
        "completed": priority_counts["P5_completed_ready_for_audit"]
    }

    return {
        "summary": summary,
        "queue": queue
    }


def get_queue_filepath(storage_dir: str, dataset: str) -> str:
    safe_name = "gold" if dataset == "gold" else "t1"
    return os.path.join(storage_dir, f"work_queue_{safe_name}.json")


def save_persistent_queue(storage_dir: str, dataset: str, queue_data: dict) -> bool:
    """
    Persists work queue state to disk atomically so it is recoverable across server restarts.
    """
    os.makedirs(storage_dir, exist_ok=True)
    filepath = get_queue_filepath(storage_dir, dataset)
    temp_file = filepath + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(queue_data, f, indent=2)
    os.replace(temp_file, filepath)
    return True


def load_persistent_queue(storage_dir: str, dataset: str) -> dict | None:
    """
    Loads saved work queue state from disk if present.
    """
    filepath = get_queue_filepath(storage_dir, dataset)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: could not load persistent queue from {filepath}: {e}")
    return None


def sync_and_persist_work_queue(manifest: list, annotations: dict, storage_dir: str, dataset: str = "t1") -> dict:
    """
    Computes and atomically saves the authoritative persistent work queue.
    """
    queue_data = build_work_queue(manifest, annotations, dataset)
    save_persistent_queue(storage_dir, dataset, queue_data)
    return queue_data
