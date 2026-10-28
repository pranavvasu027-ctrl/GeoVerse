"""
Safe, Repeatable Annotation Migration and Reconciliation Utility.
GeoVerse Model 1 — LULC Urban Growth.

Migrates reference data and human annotations from local JSON storage to Supabase/PostgreSQL.
Adheres strictly to the GeoVerse research protocol and database safety rules:
1. Supports dry-run execution by default (--mode dry-run).
2. Explicit confirmation (--confirm) is strictly required before any database writes.
3. Validates every annotation record against schema.py rules before migration.
4. Pre-import collision detection distinguishes:
   - to_insert: Destination record does not exist
   - already_reconciled: Destination record exists and all 8 fields match (skipped)
   - conflicts: Destination record exists and fields differ (halts migration, never overwrites)
   - invalid_destination: Destination record exists with invalid structure
5. Semantic review flagging: Flags unusual but syntactically valid records (e.g. uncertain with >=75% share)
   for photo-interpreter review without failing validation.
6. Quarantine support: Schema-violating records (e.g. T2-0002 2020 ambiguous without notes) are quarantined
   with explicit remediation guidance; migration status reports PARTIAL_MIGRATION_WITH_QUARANTINE.
7. Original JSON files and backups are preserved 100% untouched.
8. Conducts exhaustive field-by-field post-migration reconciliation.
"""

import os
import sys
import json
import hashlib
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set

from .schema import EPOCHS, validate_epoch_annotation
from .storage import (
    BaseAnnotationStore,
    JsonAnnotationStore,
    SupabaseAnnotationStore,
    StorageWriteError,
    StorageValidationError,
    StorageConfigurationError
)


def compute_file_hash(filepath: str) -> Optional[str]:
    """Computes SHA-256 hash of a file to verify zero modification."""
    if not os.path.exists(filepath):
        return None
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_annotation_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes annotation record fields for stable equality comparison across all 8 persisted fields.
    """
    def _str_val(v):
        return "" if v is None else str(v).strip()

    conf = rec.get("confidence_1to3")
    conf_int = None
    if conf is not None and conf != "":
        try:
            conf_int = int(conf)
        except (ValueError, TypeError):
            conf_int = None

    second_class = _str_val(rec.get("second_class"))
    if not second_class or second_class == "none":
        second_class = "none"

    return {
        "status": _str_val(rec.get("status")),
        "dominant_class": _str_val(rec.get("dominant_class")),
        "dominant_share_3bins": _str_val(rec.get("dominant_share_3bins")),
        "second_class": second_class,
        "confidence_1to3": conf_int,
        "imagery_source": _str_val(rec.get("imagery_source")),
        "imagery_date": _str_val(rec.get("imagery_date")),
        "notes": _str_val(rec.get("notes"))
    }


def compare_annotation_records(
    source_rec: Dict[str, Any],
    dest_rec: Dict[str, Any]
) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
    """
    Compares normalized source and destination records across all 8 persisted fields:
    status, dominant_class, dominant_share_3bins, second_class, confidence_1to3,
    imagery_source, imagery_date, notes.
    Returns (is_match, diff_dict).
    """
    s_norm = normalize_annotation_record(source_rec)
    d_norm = normalize_annotation_record(dest_rec)

    diffs = {}
    for field in [
        "status",
        "dominant_class",
        "dominant_share_3bins",
        "second_class",
        "confidence_1to3",
        "imagery_source",
        "imagery_date",
        "notes"
    ]:
        if s_norm[field] != d_norm[field]:
            diffs[field] = {
                "source": s_norm[field],
                "destination": d_norm[field]
            }

    return (len(diffs) == 0, diffs)


def inventory_sources(data_dir: str, storage_dir: str) -> Dict[str, Any]:
    """
    Inventories manifests, annotations, and backup archives.
    Counts samples, annotated samples, total epoch annotations, and status distribution.
    """
    inventory = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "manifests": {},
        "annotations": {},
        "backups": {},
        "totals": {
            "total_manifest_samples": 0,
            "total_annotated_samples": 0,
            "total_epoch_annotations": 0,
            "by_status": {"done": 0, "unavailable": 0, "skipped": 0, "other": 0}
        }
    }

    # Manifests
    for ds in ["t1", "gold"]:
        mpath = os.path.join(data_dir, f"{ds}_manifest.json")
        if os.path.exists(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            sample_ids = [s["anon_id"] for s in manifest_data]
            unique_ids = set(sample_ids)
            inventory["manifests"][ds] = {
                "path": mpath,
                "file_hash_sha256": compute_file_hash(mpath),
                "total_samples": len(sample_ids),
                "unique_samples": len(unique_ids),
                "duplicate_ids": [aid for aid in unique_ids if sample_ids.count(aid) > 1]
            }
            inventory["totals"]["total_manifest_samples"] += len(sample_ids)
        else:
            inventory["manifests"][ds] = {
                "path": mpath,
                "total_samples": 0,
                "exists": False
            }

    # Annotations
    for ds in ["t1", "gold"]:
        apath = os.path.join(storage_dir, f"{ds}_annotations.json")
        if os.path.exists(apath):
            with open(apath, "r", encoding="utf-8") as f:
                ann_data = json.load(f)
            sample_count = len(ann_data)
            epoch_count = 0
            status_dist = {"done": 0, "unavailable": 0, "skipped": 0, "other": 0}
            epoch_dist = {str(ep): 0 for ep in EPOCHS}

            for aid, rec in ann_data.items():
                epochs = rec.get("epochs", {})
                for ep_str, ep_val in epochs.items():
                    epoch_count += 1
                    if ep_str in epoch_dist:
                        epoch_dist[ep_str] += 1
                    st = ep_val.get("status", "")
                    if st in status_dist:
                        status_dist[st] += 1
                    else:
                        status_dist["other"] += 1

            inventory["annotations"][ds] = {
                "path": apath,
                "file_hash_sha256": compute_file_hash(apath),
                "total_samples": sample_count,
                "total_epoch_annotations": epoch_count,
                "status_distribution": status_dist,
                "epoch_distribution": epoch_dist,
                "sample_ids": sorted(list(ann_data.keys()))
            }
            inventory["totals"]["total_annotated_samples"] += sample_count
            inventory["totals"]["total_epoch_annotations"] += epoch_count
            for k in status_dist:
                inventory["totals"]["by_status"][k] += status_dist[k]
        else:
            inventory["annotations"][ds] = {
                "path": apath,
                "file_hash_sha256": None,
                "total_samples": 0,
                "total_epoch_annotations": 0,
                "exists": False
            }

    # Backups
    backup_dir = os.path.join(storage_dir, "backups")
    if os.path.exists(backup_dir):
        backup_files = [
            f for f in os.listdir(backup_dir)
            if f.endswith(".json") and os.path.isfile(os.path.join(backup_dir, f))
        ]
        inventory["backups"] = {
            "backup_dir": backup_dir,
            "backup_count": len(backup_files),
            "files": sorted(backup_files)
        }
    else:
        inventory["backups"] = {"backup_dir": backup_dir, "backup_count": 0, "files": []}

    return inventory


def validate_sources(data_dir: str, storage_dir: str) -> Dict[str, Any]:
    """
    Validates all manifest samples and existing annotations against schema.py.
    Checks for:
    - Unmanifested sample IDs
    - Invalid land-cover classes
    - Invalid area share bins or confidence ratings
    - Confidence caps on Landsat_context
    - Date window compliance (+/- 2 calendar years)
    - Mandatory notes for 'other' and 'ambiguous'
    - Semantic review flags for unusual but permitted records (e.g. uncertain with >=75% share)
    """
    validation_report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "datasets": {},
        "total_errors": 0,
        "total_warnings": 0,
        "total_semantic_flags": 0,
        "is_valid": True
    }

    for ds in ["t1", "gold"]:
        mpath = os.path.join(data_dir, f"{ds}_manifest.json")
        apath = os.path.join(storage_dir, f"{ds}_annotations.json")

        manifest_ids = set()
        if os.path.exists(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            manifest_ids = {s["anon_id"] for s in manifest_data}

        ann_data = {}
        if os.path.exists(apath):
            with open(apath, "r", encoding="utf-8") as f:
                ann_data = json.load(f)

        ds_errors = []
        ds_warnings = []
        ds_semantic_flags = []
        unmanifested = []

        for aid, rec in ann_data.items():
            if aid not in manifest_ids:
                unmanifested.append(aid)
                ds_errors.append(f"Annotation record '{aid}' is not present in {ds}_manifest.json.")

            epochs = rec.get("epochs", {})
            for ep_str, ep_val in epochs.items():
                try:
                    ep_int = int(ep_str)
                    is_valid, errs, warns = validate_epoch_annotation(ep_int, ep_val)
                    if not is_valid:
                        for err in errs:
                            ds_errors.append(f"Sample {aid} epoch {ep_str}: {err}")
                    for warn in warns:
                        ds_warnings.append(f"Sample {aid} epoch {ep_str}: {warn}")

                    # Semantic review flagging: uncertain with high share (>=50% or >=75%)
                    dom_class = ep_val.get("dominant_class", "")
                    dom_share = ep_val.get("dominant_share_3bins", "")
                    if dom_class == "uncertain" and dom_share in (">=75", "50-75"):
                        semantic_msg = (
                            f"Sample {aid} epoch {ep_str}: Semantic review flag - dominant_class is 'uncertain' "
                            f"with high share '{dom_share}'. Syntactically permitted under schema, "
                            f"flagged for photo-interpreter review."
                        )
                        ds_warnings.append(semantic_msg)
                        ds_semantic_flags.append({
                            "dataset_id": ds,
                            "anon_id": aid,
                            "epoch": ep_int,
                            "flag": "uncertain_with_high_share",
                            "dominant_class": dom_class,
                            "dominant_share_3bins": dom_share,
                            "confidence_1to3": ep_val.get("confidence_1to3"),
                            "reason": "Dominant class is 'uncertain' despite high area share (>=50%). Valid under schema, flagged for interpreter verification."
                        })

                except ValueError:
                    ds_errors.append(f"Sample {aid}: Invalid non-integer epoch key '{ep_str}'.")

        validation_report["datasets"][ds] = {
            "unmanifested_ids": unmanifested,
            "errors": ds_errors,
            "warnings": ds_warnings,
            "semantic_flags": ds_semantic_flags,
            "errors_count": len(ds_errors),
            "warnings_count": len(ds_warnings),
            "semantic_flags_count": len(ds_semantic_flags),
            "is_valid": len(ds_errors) == 0
        }
        validation_report["total_errors"] += len(ds_errors)
        validation_report["total_warnings"] += len(ds_warnings)
        validation_report["total_semantic_flags"] += len(ds_semantic_flags)

    validation_report["is_valid"] = validation_report["total_errors"] == 0
    return validation_report


def build_migration_plan(
    data_dir: str,
    storage_dir: str,
    target_store: Optional[BaseAnnotationStore] = None,
    dataset_filter: str = "all",
    skip_invalid: bool = False
) -> Dict[str, Any]:
    """
    Constructs an explicit, auditable migration plan with pre-import collision detection.
    Identifies:
    1. to_insert: Records that do not exist in destination DB.
    2. already_reconciled: Records that exist in destination and all 8 fields match (skipped to avoid unnecessary writes).
    3. conflicts: Records that exist in destination but have differing field values (blocks migration).
    4. invalid_destination: Records that exist in destination with corrupt/invalid structure.
    5. quarantined_records: Source records failing schema validation (quarantined when skip_invalid=True).
    6. semantic_review_flags: Syntactically valid records flagged for interpreter review.
    """
    inv = inventory_sources(data_dir, storage_dir)
    val = validate_sources(data_dir, storage_dir)

    target_datasets = ["t1", "gold"] if dataset_filter == "all" else [dataset_filter]

    plan = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_filter": dataset_filter,
        "skip_invalid": skip_invalid,
        "validation_passed": val["is_valid"],
        "validation_errors_count": val["total_errors"],
        "datasets_to_seed": [],
        "samples_to_sync": {},
        "annotations_to_migrate": {},
        "quarantined_records": {},
        "semantic_review_flags": [],
        "target_status": {
            "connected": False,
            "backend": target_store.get_backend_name() if target_store else "none",
            "destination_inspected": False
        },
        "actions": {
            "to_insert": [],
            "already_reconciled": [],
            "conflicts": [],
            "invalid_destination": [],
            "extra_in_destination": []
        },
        "action_summary": {
            "datasets_count": len(target_datasets),
            "samples_count": 0,
            "annotations_count": 0,
            "quarantined_count": 0,
            "to_insert_count": 0,
            "already_reconciled_count": 0,
            "conflicts_count": 0,
            "invalid_destination_count": 0,
            "extra_in_destination_count": 0,
            "semantic_review_flags_count": val.get("total_semantic_flags", 0)
        },
        "can_proceed": False,
        "blockers": []
    }

    # Aggregate semantic review flags
    for ds, rep in val["datasets"].items():
        if ds in target_datasets:
            plan["semantic_review_flags"].extend(rep.get("semantic_flags", []))

    # Check store connectivity if provided
    destination_annotations: Dict[str, Dict[str, Any]] = {}
    if target_store:
        try:
            plan["target_status"]["connected"] = target_store.ping()
        except Exception as e:
            plan["target_status"]["connected"] = False
            plan["blockers"].append(f"Target store connection failed: {e}")

        if plan["target_status"]["connected"]:
            try:
                for ds in target_datasets:
                    destination_annotations[ds] = target_store.load_annotations(ds)
                plan["target_status"]["destination_inspected"] = True
            except Exception as e:
                plan["target_status"]["destination_inspected"] = False
                plan["blockers"].append(f"Failed to inspect destination store annotations: {e}")
    else:
        plan["blockers"].append(
            "Target store is not connected. Pre-import collision check against destination database could not be performed."
        )

    # Datasets metadata
    dataset_meta = {
        "t1": {
            "dataset_id": "t1",
            "name": "T1 Training and Tuning Dataset",
            "is_training_allowed": True,
            "total_samples": 699
        },
        "gold": {
            "dataset_id": "gold",
            "name": "Tier-A Gold Evaluation Benchmark Dataset",
            "is_training_allowed": False,
            "total_samples": 641
        }
    }

    for ds in target_datasets:
        plan["datasets_to_seed"].append(dataset_meta[ds])

        # Manifest samples
        mpath = os.path.join(data_dir, f"{ds}_manifest.json")
        samples_list = []
        if os.path.exists(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                samples_list = json.load(f)
        plan["samples_to_sync"][ds] = len(samples_list)
        plan["action_summary"]["samples_count"] += len(samples_list)

        # Annotations
        apath = os.path.join(storage_dir, f"{ds}_annotations.json")
        ann_data = {}
        if os.path.exists(apath):
            with open(apath, "r", encoding="utf-8") as f:
                ann_data = json.load(f)

        records_to_migrate = []
        quarantined = []
        for aid, rec in ann_data.items():
            epochs = rec.get("epochs", {})
            for ep_str, ep_val in epochs.items():
                record_dict = {
                    "dataset_id": ds,
                    "anon_id": aid,
                    "epoch": int(ep_str),
                    "status": ep_val.get("status", ""),
                    "dominant_class": ep_val.get("dominant_class", ""),
                    "dominant_share_3bins": ep_val.get("dominant_share_3bins", ""),
                    "second_class": ep_val.get("second_class", "none"),
                    "confidence_1to3": ep_val.get("confidence_1to3"),
                    "imagery_source": ep_val.get("imagery_source", ""),
                    "imagery_date": ep_val.get("imagery_date", ""),
                    "notes": ep_val.get("notes", "")
                }
                is_valid, errs, warns = validate_epoch_annotation(int(ep_str), ep_val)
                if not is_valid:
                    if skip_invalid:
                        quarantined.append({
                            "record": record_dict,
                            "errors": errs,
                            "warnings": warns,
                            "remediation_guidance": (
                                f"Human photo-interpreter must inspect sample {aid} (epoch {ep_str}). "
                                f"Errors: {'; '.join(errs)}"
                            )
                        })
                    else:
                        records_to_migrate.append(record_dict)
                else:
                    records_to_migrate.append(record_dict)

        plan["annotations_to_migrate"][ds] = {
            "sample_count": len(ann_data),
            "epoch_records_count": len(records_to_migrate),
            "records": records_to_migrate
        }
        plan["quarantined_records"][ds] = quarantined
        plan["action_summary"]["annotations_count"] += len(records_to_migrate)
        plan["action_summary"]["quarantined_count"] += len(quarantined)

        # Pre-import collision classification against destination records
        if plan["target_status"]["destination_inspected"]:
            dest_data = destination_annotations.get(ds, {})

            for rec in records_to_migrate:
                aid = rec["anon_id"]
                ep_str = str(rec["epoch"])

                if aid not in dest_data or ep_str not in dest_data[aid].get("epochs", {}):
                    # Case 1: Destination record does not exist
                    plan["actions"]["to_insert"].append(rec)
                else:
                    dest_ep_val = dest_data[aid]["epochs"][ep_str]
                    if not isinstance(dest_ep_val, dict):
                        # Case 4: Destination record exists but structure is invalid
                        plan["actions"]["invalid_destination"].append({
                            "record": rec,
                            "destination": dest_ep_val,
                            "issue": "Destination epoch annotation is not a valid dictionary object"
                        })
                    else:
                        is_match, diffs = compare_annotation_records(rec, dest_ep_val)
                        if is_match:
                            # Case 2: Destination record exists and all 8 fields match exactly
                            plan["actions"]["already_reconciled"].append(rec)
                        else:
                            # Case 3: Destination record exists and fields differ (conflict)
                            plan["actions"]["conflicts"].append({
                                "dataset_id": ds,
                                "anon_id": aid,
                                "epoch": rec["epoch"],
                                "differences": diffs,
                                "source_record": rec,
                                "destination_record": dest_ep_val
                            })

            # Check for extra records in destination
            for d_aid, d_sample in dest_data.items():
                d_epochs = d_sample.get("epochs", {})
                for d_ep_str, d_ep_val in d_epochs.items():
                    if d_aid not in ann_data or d_ep_str not in ann_data[d_aid].get("epochs", {}):
                        plan["actions"]["extra_in_destination"].append({
                            "dataset_id": ds,
                            "anon_id": d_aid,
                            "epoch": int(d_ep_str) if d_ep_str.isdigit() else d_ep_str,
                            "destination_record": d_ep_val
                        })
        else:
            # Fallback when destination could not be inspected
            plan["actions"]["to_insert"].extend(records_to_migrate)

    # Update summary counts
    plan["action_summary"]["to_insert_count"] = len(plan["actions"]["to_insert"])
    plan["action_summary"]["already_reconciled_count"] = len(plan["actions"]["already_reconciled"])
    plan["action_summary"]["conflicts_count"] = len(plan["actions"]["conflicts"])
    plan["action_summary"]["invalid_destination_count"] = len(plan["actions"]["invalid_destination"])
    plan["action_summary"]["extra_in_destination_count"] = len(plan["actions"]["extra_in_destination"])

    if not val["is_valid"] and not skip_invalid:
        plan["blockers"].append(
            f"Validation failed with {val['total_errors']} schema errors. "
            "Resolve records in JSON or use --skip-invalid to migrate only verified records."
        )

    if plan["action_summary"]["conflicts_count"] > 0:
        plan["blockers"].append(
            f"Pre-import collision detection detected {plan['action_summary']['conflicts_count']} "
            "conflicting records in destination database. Aborting to prevent silent overwrites."
        )

    if plan["action_summary"]["invalid_destination_count"] > 0:
        plan["blockers"].append(
            f"Destination database contains {plan['action_summary']['invalid_destination_count']} "
            "records with invalid structures."
        )

    plan["can_proceed"] = (
        len(plan["blockers"]) == 0
        and plan["target_status"]["connected"]
        and plan["target_status"]["destination_inspected"]
        and plan["action_summary"]["conflicts_count"] == 0
    )
    return plan


def reconcile_annotations(
    source_annotations: Dict[str, Any],
    destination_annotations: Dict[str, Any],
    quarantined_keys: Optional[Any] = None,
    quarantined_details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compares source JSON annotations with destination DB annotations field-by-field.
    Verifies 100% data fidelity:
    - Dominant class
    - Dominant share
    - Second class
    - Confidence level
    - Imagery source
    - Imagery date
    - Status
    - Notes
    Accounts for quarantined records pending remediation (does not mark them as unknown mismatches).
    """
    quarantined_set = set()
    details_map = dict(quarantined_details or {})
    if isinstance(quarantined_keys, dict):
        quarantined_set.update(quarantined_keys.keys())
        if not details_map:
            details_map = quarantined_keys
    elif quarantined_keys:
        for item in quarantined_keys:
            if isinstance(item, str):
                quarantined_set.add(item)
            elif isinstance(item, dict) and "record" in item:
                rec = item["record"]
                k1 = f"{rec.get('anon_id')}:{rec.get('epoch')}"
                k2 = f"{rec.get('dataset_id')}:{rec.get('anon_id')}:{rec.get('epoch')}"
                quarantined_set.add(k1)
                quarantined_set.add(k2)
                details_map[k1] = item
                details_map[k2] = item

    reconciliation = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_source_samples": len(source_annotations),
        "total_dest_samples": len(destination_annotations),
        "total_source_epoch_records": 0,
        "total_dest_epoch_records": 0,
        "exact_matches": 0,
        "mismatches": [],
        "missing_in_destination": [],
        "extra_in_destination": [],
        "quarantined_pending_remediation": [],
        "is_fully_reconciled": False
    }

    fields_to_compare = [
        "status",
        "dominant_class",
        "dominant_share_3bins",
        "second_class",
        "confidence_1to3",
        "imagery_source",
        "imagery_date",
        "notes"
    ]

    for aid, s_rec in source_annotations.items():
        s_epochs = s_rec.get("epochs", {})
        reconciliation["total_source_epoch_records"] += len(s_epochs)

        # Check if entire sample is missing in destination
        if aid not in destination_annotations:
            # Check if all its epochs were intentionally quarantined
            non_quarantined_epochs = []
            for ep_str in s_epochs.keys():
                key1 = f"{aid}:{ep_str}"
                raw_aid = aid.split(":")[-1] if ":" in aid else aid
                key2 = f"{raw_aid}:{ep_str}"
                if key1 in quarantined_set or key2 in quarantined_set:
                    q_info = details_map.get(key1) or details_map.get(key2) or {}
                    reconciliation["quarantined_pending_remediation"].append({
                        "dataset_id": aid.split(":")[0] if ":" in aid else "unknown",
                        "anon_id": raw_aid,
                        "epoch": int(ep_str) if str(ep_str).isdigit() else ep_str,
                        "issue": "Excluded from migration due to schema validation failure; pending remediation",
                        "validation_errors": q_info.get("errors", []),
                        "remediation_guidance": q_info.get("remediation_guidance", ""),
                        "status": "QUARANTINED"
                    })
                else:
                    non_quarantined_epochs.append(ep_str)

            if non_quarantined_epochs:
                reconciliation["missing_in_destination"].append(aid)
            continue

        d_rec = destination_annotations[aid]
        d_epochs = d_rec.get("epochs", {})

        for ep_str, s_val in s_epochs.items():
            key1 = f"{aid}:{ep_str}"
            raw_aid = aid.split(":")[-1] if ":" in aid else aid
            key2 = f"{raw_aid}:{ep_str}"

            if key1 in quarantined_set or key2 in quarantined_set:
                q_info = details_map.get(key1) or details_map.get(key2) or {}
                reconciliation["quarantined_pending_remediation"].append({
                    "dataset_id": aid.split(":")[0] if ":" in aid else "unknown",
                    "anon_id": raw_aid,
                    "epoch": int(ep_str) if str(ep_str).isdigit() else ep_str,
                    "issue": "Excluded from migration due to schema validation failure; pending remediation",
                    "validation_errors": q_info.get("errors", []),
                    "remediation_guidance": q_info.get("remediation_guidance", ""),
                    "status": "QUARANTINED"
                })
                continue

            if ep_str not in d_epochs:
                reconciliation["mismatches"].append({
                    "anon_id": aid,
                    "epoch": ep_str,
                    "issue": "Missing epoch in destination"
                })
                continue

            d_val = d_epochs[ep_str]
            field_diffs = {}
            for f in fields_to_compare:
                sv = s_val.get(f)
                dv = d_val.get(f)

                # Normalize none and empty strings
                if f == "second_class":
                    sv = sv or "none"
                    dv = dv or "none"
                else:
                    sv = "" if sv is None else sv
                    dv = "" if dv is None else dv

                # Normalize confidence integers
                if f == "confidence_1to3":
                    sv = int(sv) if sv not in ("", None) else None
                    dv = int(dv) if dv not in ("", None) else None

                if sv != dv:
                    field_diffs[f] = {"source": sv, "destination": dv}

            if field_diffs:
                reconciliation["mismatches"].append({
                    "anon_id": aid,
                    "epoch": ep_str,
                    "differences": field_diffs
                })
            else:
                reconciliation["exact_matches"] += 1

    for aid, d_rec in destination_annotations.items():
        d_epochs = d_rec.get("epochs", {})
        reconciliation["total_dest_epoch_records"] += len(d_epochs)
        if aid not in source_annotations:
            reconciliation["extra_in_destination"].append(aid)

    accounted_source_records = (
        reconciliation["exact_matches"] + len(reconciliation["quarantined_pending_remediation"])
    )
    reconciliation["is_fully_reconciled"] = (
        len(reconciliation["mismatches"]) == 0
        and len(reconciliation["missing_in_destination"]) == 0
        and len(reconciliation["extra_in_destination"]) == 0
        and accounted_source_records == reconciliation["total_source_epoch_records"]
    )
    return reconciliation


def execute_migration(
    plan: Dict[str, Any],
    store: BaseAnnotationStore,
    confirm: bool = False,
    data_dir: Optional[str] = None,
    storage_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes database migration from the generated plan.
    Strict fail-closed safety guards:
    - Aborts if confirm is False.
    - Aborts if validation did not pass.
    - Aborts if destination collisions exist (never silently overwrites divergent records).
    - Skips already reconciled identical records to prevent unnecessary writes.
    - Quarantined records result in PARTIAL_MIGRATION_WITH_QUARANTINE status.
    - Preserves original JSON files unchanged (verifies pre- and post-hashes).
    """
    if not confirm:
        raise StorageWriteError(
            "Migration execution aborted: --confirm flag is strictly required to authorize database writes."
        )

    if not plan.get("target_status", {}).get("destination_inspected", False):
        raise StorageWriteError(
            "Migration execution aborted: destination pre-import inspection was not performed or failed. "
            "Failing closed to prevent unverified writes."
        )

    if not plan.get("validation_passed", False) and not plan.get("skip_invalid", False):
        raise StorageValidationError(
            f"Cannot execute migration: plan contains {plan.get('validation_errors_count', 0)} schema errors."
        )

    conflicts = plan.get("actions", {}).get("conflicts", [])
    if len(conflicts) > 0:
        raise StorageWriteError(
            f"Migration execution aborted: {len(conflicts)} pre-import collisions detected. "
            "Silently overwriting divergent destination records is strictly forbidden."
        )

    # 1. Record source JSON file hashes before migration
    base_dir = Path(__file__).parent.resolve()
    s_dir = storage_dir or str(base_dir / "storage")
    t1_hash_before = compute_file_hash(os.path.join(s_dir, "t1_annotations.json"))
    gold_hash_before = compute_file_hash(os.path.join(s_dir, "gold_annotations.json"))

    execution_report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "datasets_seeded": 0,
        "samples_synced": 0,
        "annotations_synced": 0,
        "annotations_inserted": 0,
        "skipped_identical": 0,
        "conflicts": conflicts,
        "quarantined_records_count": plan.get("action_summary", {}).get("quarantined_count", 0),
        "quarantined_records": plan.get("quarantined_records", {}),
        "errors": [],
        "reconciliation": None,
        "source_json_unmodified": True,
        "status": "FAILED"
    }

    try:
        # Step A: Seed datasets
        if hasattr(store, "client"):
            client = store.client
            for ds_info in plan["datasets_to_seed"]:
                client.table("datasets").upsert({
                    "dataset_id": ds_info["dataset_id"],
                    "name": ds_info["name"],
                    "description": f"GeoVerse Model 1 {ds_info['name']}",
                    "is_training_allowed": ds_info["is_training_allowed"],
                    "total_samples": ds_info["total_samples"]
                }, on_conflict="dataset_id").execute()
                execution_report["datasets_seeded"] += 1

        # Step B: Sync samples from manifests
        d_dir = data_dir or str(base_dir / "data")
        for ds in plan["samples_to_sync"]:
            mpath = os.path.join(d_dir, f"{ds}_manifest.json")
            if os.path.exists(mpath) and hasattr(store, "client"):
                with open(mpath, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                client = store.client

                # Batch insert samples (chunks of 100)
                batch = []
                for s in manifest:
                    batch.append({
                        "dataset_id": ds,
                        "anon_id": s["anon_id"],
                        "lat": float(s["lat"]),
                        "lon": float(s["lon"]),
                        "polygon": s.get("polygon", []),
                        "inside_primary_landsat": True,
                        "is_double_interpretation": False
                    })
                    if len(batch) >= 100:
                        client.table("samples").upsert(batch, on_conflict="dataset_id,anon_id").execute()
                        execution_report["samples_synced"] += len(batch)
                        batch = []
                if batch:
                    client.table("samples").upsert(batch, on_conflict="dataset_id,anon_id").execute()
                    execution_report["samples_synced"] += len(batch)

        # Step C: Sync annotations
        # Only write records classified as to_insert. Records in already_reconciled are skipped.
        records_to_insert = plan.get("actions", {}).get("to_insert", [])
        records_skipped = plan.get("actions", {}).get("already_reconciled", [])
        execution_report["skipped_identical"] = len(records_skipped)

        # Group records to insert by (dataset, sample)
        samples_grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for rec in records_to_insert:
            ds = rec["dataset_id"]
            aid = rec["anon_id"]
            key = (ds, aid)
            if key not in samples_grouped:
                samples_grouped[key] = {"epochs": {}}
            samples_grouped[key]["epochs"][str(rec["epoch"])] = {
                "status": rec["status"],
                "dominant_class": rec["dominant_class"],
                "dominant_share_3bins": rec["dominant_share_3bins"],
                "second_class": rec["second_class"],
                "confidence_1to3": rec["confidence_1to3"],
                "imagery_source": rec["imagery_source"],
                "imagery_date": rec["imagery_date"],
                "notes": rec["notes"]
            }

        for (ds, aid), sample_payload in samples_grouped.items():
            store.save_sample_annotation(ds, aid, sample_payload, annotator_id="migration_pipeline")
            execution_report["annotations_inserted"] += len(sample_payload["epochs"])

        execution_report["annotations_synced"] = (
            execution_report["annotations_inserted"] + execution_report["skipped_identical"]
        )

        # Step D: Reconcile source JSON vs destination DB
        source_json_store = JsonAnnotationStore(storage_dir=s_dir)
        source_all = {}
        dest_all = {}
        for ds in plan["samples_to_sync"]:
            s_data = source_json_store.load_annotations(ds)
            d_data = store.load_annotations(ds)
            source_all.update({f"{ds}:{k}": v for k, v in s_data.items()})
            dest_all.update({f"{ds}:{k}": v for k, v in d_data.items()})

        # Build quarantined key set and details map for reconciliation
        quarantined_keys = set()
        quarantined_details = {}
        for ds, q_list in plan.get("quarantined_records", {}).items():
            for q_item in q_list:
                q_rec = q_item["record"]
                k1 = f"{ds}:{q_rec['anon_id']}:{q_rec['epoch']}"
                k2 = f"{q_rec['anon_id']}:{q_rec['epoch']}"
                quarantined_keys.add(k1)
                quarantined_keys.add(k2)
                quarantined_details[k1] = q_item
                quarantined_details[k2] = q_item

        reconcile_res = reconcile_annotations(
            source_all,
            dest_all,
            quarantined_keys=quarantined_keys,
            quarantined_details=quarantined_details
        )
        execution_report["reconciliation"] = reconcile_res

        if reconcile_res["is_fully_reconciled"]:
            if execution_report["quarantined_records_count"] > 0:
                execution_report["status"] = "PARTIAL_MIGRATION_WITH_QUARANTINE"
            else:
                execution_report["status"] = "SUCCESS"
        else:
            execution_report["status"] = "RECONCILIATION_MISMATCH"

    except Exception as e:
        execution_report["errors"].append(str(e))
        execution_report["status"] = "ERROR"
        raise

    finally:
        # Step E: Verify original JSON files were never modified
        t1_hash_after = compute_file_hash(os.path.join(s_dir, "t1_annotations.json"))
        gold_hash_after = compute_file_hash(os.path.join(s_dir, "gold_annotations.json"))

        t1_intact = (t1_hash_before == t1_hash_after)
        gold_intact = (gold_hash_before == gold_hash_after)
        execution_report["source_json_unmodified"] = t1_intact and gold_intact

        if not (t1_intact and gold_intact):
            execution_report["errors"].append("CRITICAL: Source JSON hash mismatch detected post-migration!")
            execution_report["status"] = "INTEGRITY_COMPROMISED"

    return execution_report


def main():
    parser = argparse.ArgumentParser(
        description="GeoVerse Model 1 — Safe Supabase Annotation Migration and Reconciliation"
    )
    parser.add_argument(
        "--mode",
        choices=["inventory", "validate", "dry-run", "migrate", "reconcile"],
        default="dry-run",
        help="Execution mode (default: dry-run)"
    )
    parser.add_argument(
        "--dataset",
        choices=["all", "t1", "gold"],
        default="all",
        help="Dataset scope (default: all)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Explicit confirmation required to execute database writes in migrate mode"
    )
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Quarantine invalid records during migration instead of failing the entire plan"
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Custom path to data directory containing manifests"
    )
    parser.add_argument(
        "--storage-dir",
        default=None,
        help="Custom path to JSON storage directory"
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Path to save detailed JSON output report"
    )

    args = parser.parse_args()

    base_dir = Path(__file__).parent.resolve()
    data_dir = args.data_dir or str(base_dir / "data")
    storage_dir = args.storage_dir or str(base_dir / "storage")

    print("=" * 72)
    print(" GeoVerse Model 1 — Supabase Annotation Migration & Audit Engine")
    print("=" * 72)
    print(f"Mode:        {args.mode.upper()}")
    print(f"Dataset:     {args.dataset}")
    print(f"Data Dir:    {data_dir}")
    print(f"Storage Dir: {storage_dir}")
    print("-" * 72)

    if args.mode == "inventory":
        inv = inventory_sources(data_dir, storage_dir)
        print(json.dumps(inv, indent=2))
        return

    if args.mode == "validate":
        val = validate_sources(data_dir, storage_dir)
        print(f"Validation Status:    {'PASS' if val['is_valid'] else 'FAIL'}")
        print(f"Total Errors:         {val['total_errors']}")
        print(f"Total Warnings:       {val['total_warnings']}")
        print(f"Semantic Flags:       {val.get('total_semantic_flags', 0)}")
        if val["total_errors"] > 0:
            print("\nErrors:")
            for ds, rep in val["datasets"].items():
                for err in rep["errors"]:
                    print(f"  [{ds.upper()}] {err}")
        if val.get("total_semantic_flags", 0) > 0:
            print("\nSemantic Review Flags (syntactically permitted):")
            for ds, rep in val["datasets"].items():
                for flag in rep.get("semantic_flags", []):
                    print(f"  [{ds.upper()}] Sample {flag['anon_id']} epoch {flag['epoch']}: {flag['reason']}")
        return

    # Dry-run or Migrate
    store = None
    try:
        store = SupabaseAnnotationStore(manifest_dir=data_dir, storage_dir=storage_dir)
    except Exception as e:
        print(f"Note: Live Supabase backend is not configured: {e}")
        print("Using local assessment mode for plan generation.")

    plan = build_migration_plan(
        data_dir,
        storage_dir,
        target_store=store,
        dataset_filter=args.dataset,
        skip_invalid=args.skip_invalid
    )

    print("Migration Plan Summary:")
    print(f"  Validation Passed:        {plan['validation_passed']}")
    print(f"  Target Connected:         {plan['target_status']['connected']} ({plan['target_status']['backend']})")
    print(f"  Destination Inspected:    {plan['target_status']['destination_inspected']}")
    print(f"  Datasets to Seed:         {len(plan['datasets_to_seed'])}")
    print(f"  Samples to Sync:          {plan['action_summary']['samples_count']}")
    print(f"  Annotations to Process:   {plan['action_summary']['annotations_count']}")
    print(f"  -> To Insert (New):       {plan['action_summary']['to_insert_count']}")
    print(f"  -> Already Reconciled:    {plan['action_summary']['already_reconciled_count']}")
    print(f"  -> Pre-Import Conflicts:  {plan['action_summary']['conflicts_count']}")
    print(f"  -> Quarantined Records:   {plan['action_summary']['quarantined_count']}")
    print(f"  -> Semantic Review Flags: {plan['action_summary']['semantic_review_flags_count']}")

    if plan["blockers"]:
        print("\nBlockers to Migration:")
        for blk in plan["blockers"]:
            print(f"  [BLOCKER] {blk}")

    if plan.get("semantic_review_flags"):
        print("\nSemantic Review Flags (Syntactically Permitted):")
        for flag in plan["semantic_review_flags"]:
            print(f"  [SEMANTIC REVIEW] Sample {flag['anon_id']} epoch {flag['epoch']}: {flag['reason']}")

    if args.mode == "dry-run":
        print("\n[DRY-RUN] No writes were performed. Original files remain untouched.")
        if args.report_out:
            with open(args.report_out, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2)
            print(f"Report saved to {args.report_out}")
        return

    if args.mode == "migrate":
        if not args.confirm:
            print("\n[ERROR] Migration aborted: --confirm flag is required to perform production writes.")
            sys.exit(1)

        if not plan["can_proceed"]:
            print("\n[ERROR] Migration cannot proceed due to active blockers.")
            sys.exit(1)

        print("\nExecuting Migration...")
        report = execute_migration(plan, store, confirm=True, data_dir=data_dir, storage_dir=storage_dir)
        print(f"Migration Status:          {report['status']}")
        print(f"Datasets Seeded:           {report['datasets_seeded']}")
        print(f"Samples Synced:            {report['samples_synced']}")
        print(f"Annotations Inserted:      {report['annotations_inserted']}")
        print(f"Annotations Skipped (Same):{report['skipped_identical']}")
        print(f"Quarantined Records:       {report['quarantined_records_count']}")
        print(f"Source JSON Intact:        {report['source_json_unmodified']}")
        if args.report_out:
            with open(args.report_out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"Report saved to {args.report_out}")


if __name__ == "__main__":
    main()
