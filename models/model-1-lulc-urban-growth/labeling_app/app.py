import os
import json
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from .schema import (
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
from .storage import AnnotationStore
from .exporter import export_to_standard_csv
from .imagery import get_historical_imagery_info, get_all_epochs_imagery
from .qc import compute_qc_stats
from .readiness import evaluate_readiness, assert_training_allowed
from .work_queue import (
    build_work_queue,
    load_persistent_queue,
    save_persistent_queue,
    sync_and_persist_work_queue,
    get_double_interpretation_ids,
    is_inside_primary_landsat
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
VALID_DATASETS = {"t1", "gold"}

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

def get_store():
    storage_dir = app.config.get("STORAGE_DIR", STORAGE_DIR)
    return AnnotationStore(storage_dir)


def normalize_dataset(dataset):
    """Return an approved dataset identifier or ``None``.

    Dataset selection is a research-integrity boundary: defaulting an unknown
    identifier to T1 could put a Gold annotation into the training store.
    """
    return dataset if dataset in VALID_DATASETS else None


def load_manifest(dataset):
    safe_name = normalize_dataset(dataset)
    if safe_name is None:
        return None
    manifest_file = os.path.join(DATA_DIR, f"{safe_name}_manifest.json")
    if not os.path.exists(manifest_file):
        return []
    with open(manifest_file, "r", encoding="utf-8") as f:
        return json.load(f)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config")
def get_config():
    return jsonify({
        "epochs": EPOCHS,
        "definite_classes": DEFINITE_CLASSES,
        "abstain_classes": ABSTAIN_CLASSES,
        "all_classes": ALL_CLASSES,
        "share_bins": SHARE_BINS,
        "confidence_levels": CONFIDENCE_LEVELS,
        "sources_ok": SOURCES_OK,
        "status_options": STATUS_OPTIONS
    })

@app.route("/api/imagery")
def get_imagery_config():
    """
    Returns authentic historical imagery metadata and STAC tile layers for all epochs.
    """
    return jsonify(get_all_epochs_imagery())

@app.route("/api/imagery/<int:epoch>")
def get_epoch_imagery(epoch):
    """
    Returns authentic historical imagery metadata and STAC tile layer for a single epoch.
    """
    info = get_historical_imagery_info(epoch)
    if not info:
        return jsonify({"error": f"No verified imagery for epoch {epoch}"}), 404
    return jsonify(info)

@app.route("/api/manifest")
def get_manifest():
    dataset = normalize_dataset(request.args.get("dataset", "t1"))
    if dataset is None:
        return jsonify({"error": "Unknown dataset. Allowed datasets: gold, t1."}), 400
    manifest = load_manifest(dataset)
    store = get_store()
    annotations = store.load_annotations(dataset)
    double_ids = get_double_interpretation_ids(dataset)

    # Attach summary completion status and protocol flags
    items = []
    for s in manifest:
        aid = s["anon_id"]
        lat = float(s["lat"])
        lon = float(s["lon"])
        inside_primary = is_inside_primary_landsat(lat, lon)
        is_double = aid in double_ids

        ann = annotations.get(aid, {}).get("epochs", {})
        done_epochs = sum(1 for ep in EPOCHS if ann.get(str(ep), {}).get("status") in ["done", "unavailable"])
        status = "unlabeled"
        if done_epochs == len(EPOCHS):
            status = "completed"
        elif done_epochs > 0:
            status = "in_progress"

        items.append({
            "anon_id": aid,
            "lat": lat,
            "lon": lon,
            "polygon": s.get("polygon", []),
            "status": status,
            "done_epochs": done_epochs,
            "is_double_interpretation": is_double,
            "inside_primary_landsat": inside_primary
        })

    return jsonify({
        "dataset": dataset,
        "total": len(items),
        "items": items
    })

@app.route("/api/work_queue")
def get_work_queue():
    """
    Returns prioritized persistent annotation queue based on protocol rules.
    Immediately recoverable across server restarts.
    """
    dataset = normalize_dataset(request.args.get("dataset", "t1"))
    if dataset is None:
        return jsonify({"error": "Unknown dataset. Allowed datasets: gold, t1."}), 400
    storage_dir = app.config.get("STORAGE_DIR", STORAGE_DIR)
    manifest = load_manifest(dataset)
    store = get_store()
    annotations = store.load_annotations(dataset)
    
    force_sync = request.args.get("sync", "false").lower() == "true"
    queue_data = None
    if not force_sync:
        queue_data = load_persistent_queue(storage_dir, dataset)

    if not queue_data:
        queue_data = sync_and_persist_work_queue(manifest, annotations, storage_dir, dataset)

    return jsonify(queue_data)

@app.route("/api/work_queue/sync", methods=["POST"])
def force_sync_work_queue():
    """
    Explicitly re-indexes and synchronizes the persistent work queue.
    """
    dataset = normalize_dataset(request.args.get("dataset", "t1"))
    if dataset is None:
        return jsonify({"error": "Unknown dataset. Allowed datasets: gold, t1."}), 400
    storage_dir = app.config.get("STORAGE_DIR", STORAGE_DIR)
    manifest = load_manifest(dataset)
    store = get_store()
    annotations = store.load_annotations(dataset)
    queue_data = sync_and_persist_work_queue(manifest, annotations, storage_dir, dataset)
    return jsonify({
        "status": "synchronized",
        "dataset": dataset,
        "summary": queue_data["summary"]
    })

@app.route("/api/readiness")
def get_readiness():
    storage_dir = app.config.get("STORAGE_DIR", STORAGE_DIR)
    exports_dir = app.config.get("EXPORTS_DIR", EXPORTS_DIR)
    return jsonify(evaluate_readiness(storage_dir, exports_dir))

@app.route("/api/qc")
def get_qc():
    dataset = normalize_dataset(request.args.get("dataset", "t1"))
    if dataset is None:
        return jsonify({"error": "Unknown dataset. Allowed datasets: gold, t1."}), 400
    manifest = load_manifest(dataset)
    store = get_store()
    annotations = store.load_annotations(dataset)
    stats = compute_qc_stats(manifest, annotations, dataset=dataset)
    return jsonify(stats)

@app.route("/api/annotation/<dataset>/<anon_id>", methods=["GET", "POST"])
def handle_annotation(dataset, anon_id):
    dataset = normalize_dataset(dataset)
    if dataset is None:
        return jsonify({"error": "Unknown dataset. Allowed datasets: gold, t1."}), 400
    manifest = load_manifest(dataset)
    if anon_id not in {sample["anon_id"] for sample in manifest}:
        return jsonify({"error": "Unknown sample ID for this dataset."}), 404

    store = get_store()
    if request.method == "GET":
        annotations = store.load_annotations(dataset)
        sample_data = annotations.get(anon_id, {"epochs": {}})
        return jsonify(sample_data)

    elif request.method == "POST":
        payload = request.json or {}
        if "epoch" in payload and "data" in payload and "epochs" not in payload:
            epochs_data = {str(payload["epoch"]): payload["data"]}
            payload = {"epochs": epochs_data}
        else:
            epochs_data = payload.get("epochs", {})

        if not isinstance(epochs_data, dict) or not epochs_data:
            return jsonify({"status": "validation_failed", "errors": {"epochs": {
                "valid": False,
                "errors": ["At least one epoch annotation is required."],
                "warnings": []
            }}}), 400
        
        # Validate each epoch submitted
        validation_results = {}
        has_errors = False
        for ep_str, data in epochs_data.items():
            try:
                ep_int = int(ep_str)
                is_valid, errs, warns = validate_epoch_annotation(ep_int, data)
                validation_results[ep_str] = {"valid": is_valid, "errors": errs, "warnings": warns}
                if not is_valid:
                    has_errors = True
            except ValueError:
                validation_results[ep_str] = {"valid": False, "errors": [f"Invalid epoch key {ep_str}"], "warnings": []}
                has_errors = True

        if has_errors:
            return jsonify({
                "status": "validation_failed",
                "errors": validation_results
            }), 400

        # Save to atomic store (merges submitted epochs with existing epochs)
        try:
            store.save_sample_annotation(dataset, anon_id, payload)
        except Exception as e:
            return jsonify({
                "status": "storage_error",
                "error": f"Storage write failed: {str(e)}"
            }), 500
        
        # Update persistent work queue automatically
        storage_dir = app.config.get("STORAGE_DIR", STORAGE_DIR)
        annotations = store.load_annotations(dataset)
        sync_and_persist_work_queue(manifest, annotations, storage_dir, dataset)

        return jsonify({
            "status": "saved",
            "validation": validation_results,
            "epochs": annotations.get(anon_id, {}).get("epochs", {})
        })

@app.route("/api/export/<dataset>", methods=["POST"])
def export_dataset(dataset):
    safe_name = normalize_dataset(dataset)
    if safe_name is None:
        return jsonify({"error": "Unknown dataset. Allowed datasets: gold, t1."}), 400
    manifest_file = os.path.join(DATA_DIR, f"{safe_name}_manifest.json")
    if not os.path.exists(manifest_file):
        return jsonify({"error": "Manifest not found"}), 404

    store = get_store()
    annotations = store.load_annotations(dataset)
    export_csv = os.path.join(EXPORTS_DIR, f"{safe_name}_annotated_export.csv")
    summary = export_to_standard_csv(manifest_file, annotations, export_csv)
    return jsonify({
        "status": "success",
        "export_path": export_csv,
        "summary": summary
    })

def create_app(storage_dir=None):
    if storage_dir:
        app.config["STORAGE_DIR"] = storage_dir
    return app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
