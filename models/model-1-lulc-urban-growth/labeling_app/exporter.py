"""
Reference Data Exporter and Downstream Validation Service.

Produces the authoritative 35-column CSV matching ingest_gold.py schema.
Enforces pre-export validation guards:
1. Validates schema and vocabularies across all 4 epochs.
2. Checks duplicate anon_ids.
3. Checks date window constraints (epoch +/- 2 calendar years).
4. Tracks complete vs incomplete annotations without silent omission.
5. Saves timestamped backup before export and generates a sidecar validation report.
"""

import os
import json
import shutil
import time
from datetime import datetime, timezone
import pandas as pd
from .schema import EPOCHS, validate_epoch_annotation

# Authoritative 35 columns expected by ingest_gold.py
EXPORT_COLUMNS = ["anon_id", "lat", "lon"] + [
    f"{field}_{epoch}"
    for epoch in EPOCHS
    for field in (
        "dominant_class",
        "dominant_share_3bins",
        "second_class",
        "confidence_1to3",
        "imagery_source",
        "imagery_date",
        "status",
        "notes"
    )
]

def export_to_standard_csv(manifest_path: str, annotations_data: dict, output_csv_path: str) -> dict:
    """
    Exports saved annotations into the exact 35-column CSV schema expected by ingest_gold.py.
    Generates a pre-export validation report and sidecar JSON.
    """
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    seen_ids = set()
    duplicate_ids = []
    rows = []
    rejected_records = []
    
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_samples": len(manifest),
        "total_manifest_samples": len(manifest),
        "fully_labeled": 0,
        "fully_labeled_samples": 0,
        "partially_labeled": 0,
        "partially_labeled_samples": 0,
        "unlabeled": 0,
        "unlabeled_samples": 0,
        "duplicate_manifest_ids": [],
        "validation_errors_count": 0,
        "rejected_records": [],
        "is_complete_final_dataset": False
    }

    for item in manifest:
        aid = item["anon_id"]
        lat = item["lat"]
        lon = item["lon"]

        if aid in seen_ids:
            duplicate_ids.append(aid)
        seen_ids.add(aid)

        row_dict = {
            "anon_id": aid,
            "lat": lat,
            "lon": lon
        }

        sample_ann = annotations_data.get(aid, {}).get("epochs", {})
        epochs_done = 0
        sample_errors = []

        for y in EPOCHS:
            y_str = str(y)
            ann = sample_ann.get(y_str, {})
            status = ann.get("status", "")

            # If annotated, validate compliance
            if status:
                is_valid, errs, warns = validate_epoch_annotation(y, ann)
                if not is_valid:
                    sample_errors.append({"epoch": y, "errors": errs})

            # Populate wide row columns
            row_dict[f"dominant_class_{y}"] = ann.get("dominant_class", "")
            row_dict[f"dominant_share_3bins_{y}"] = ann.get("dominant_share_3bins", "")
            row_dict[f"second_class_{y}"] = ann.get("second_class", "")
            row_dict[f"confidence_1to3_{y}"] = ann.get("confidence_1to3", "")
            row_dict[f"imagery_source_{y}"] = ann.get("imagery_source", "")
            row_dict[f"imagery_date_{y}"] = ann.get("imagery_date", "")
            row_dict[f"status_{y}"] = status
            row_dict[f"notes_{y}"] = ann.get("notes", "")

            if status in ["done", "unavailable"]:
                epochs_done += 1

        if sample_errors:
            summary["validation_errors_count"] += len(sample_errors)
            rejected_records.append({
                "anon_id": aid,
                "issues": sample_errors
            })

        if epochs_done == len(EPOCHS):
            summary["fully_labeled"] += 1
            summary["fully_labeled_samples"] += 1
        elif epochs_done > 0:
            summary["partially_labeled"] += 1
            summary["partially_labeled_samples"] += 1
        else:
            summary["unlabeled"] += 1
            summary["unlabeled_samples"] += 1

        rows.append(row_dict)

    summary["duplicate_manifest_ids"] = duplicate_ids
    summary["rejected_records"] = rejected_records
    summary["is_complete_final_dataset"] = (
        summary["fully_labeled_samples"] == len(manifest) and
        summary["validation_errors_count"] == 0 and
        len(duplicate_ids) == 0
    )

    # Backup existing export file if present
    if os.path.exists(output_csv_path):
        ts = time.time_ns()
        bak_dir = os.path.join(os.path.dirname(output_csv_path), "backups")
        os.makedirs(bak_dir, exist_ok=True)
        shutil.copy2(output_csv_path, os.path.join(bak_dir, f"export_backup_{ts}.csv"))

    # Write CSV
    df = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
    os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
    df.to_csv(output_csv_path, index=False, encoding="utf-8")

    # Write sidecar validation report
    report_path = os.path.splitext(output_csv_path)[0] + "_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary
