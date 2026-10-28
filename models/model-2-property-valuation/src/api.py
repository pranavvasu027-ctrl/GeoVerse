"""
api.py
======
REST API Microservice for GeoVerse Model 2 — Property Valuation & Scenario Analysis.

Endpoints:
- GET  /api/v1/health             Health-check & Model Evaluation Metrics
- GET  /api/v1/localities         List verified Pune micro-markets & geospatial anchors
- POST /api/v1/predict            Single property price valuation & confidence interval
- POST /api/v1/compare-scenarios  What-if scenario impact & infrastructure delta analysis
"""

import os
import sys
from pathlib import Path
from flask import Flask, request, jsonify

SRC_DIR = Path(__file__).parent.resolve()
MODEL2_DIR = SRC_DIR.parent
sys.path.insert(0, str(SRC_DIR))

from real_geo_data import LOCALITIES, METRO_STATIONS, IT_HUBS, HIGHWAYS
from valuation_model import PropertyValuationModel, VALID_PROPERTY_TYPES

app = Flask(__name__)

# Initialize model pipeline once at startup
valuation_model = PropertyValuationModel()


@app.route("/api/v1/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "GeoVerse Model 2 — Property Valuation & Scenario Analytics",
        "model_version": valuation_model.version,
        "is_model_loaded": valuation_model.pipeline is not None,
        "evaluation_metrics": valuation_model.metrics,
        "localities_count": len(LOCALITIES),
        "data_provenance": "trained_on_documented_synthetic_dataset",
        "is_synthetic_training_data": True,
        "is_real_registry_transaction": False
    }), 200


@app.route("/api/v1/localities", methods=["GET"])
def get_localities():
    localities_list = []
    for name, data in LOCALITIES.items():
        localities_list.append({
            "locality_name": name,
            "latitude": data["lat"],
            "longitude": data["lon"],
            "zone": data["zone"]
        })
    return jsonify({
        "total_localities": len(localities_list),
        "localities": localities_list,
        "supported_property_types": VALID_PROPERTY_TYPES
    }), 200


@app.route("/api/v1/predict", methods=["POST"])
def predict():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    try:
        result = valuation_model.predict(payload)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": "Input validation error", "details": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Valuation prediction failed", "details": str(e)}), 500


@app.route("/api/v1/compare-scenarios", methods=["POST"])
def compare_scenarios():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    base_prop = payload.get("base_property")
    scenarios = payload.get("scenarios")

    if not isinstance(base_prop, dict):
        return jsonify({"error": "Missing or invalid 'base_property' dictionary"}), 400
    if not isinstance(scenarios, list) or len(scenarios) == 0:
        return jsonify({"error": "Missing or empty 'scenarios' list"}), 400

    try:
        comparison_res = valuation_model.compare_scenarios(base_prop, scenarios)
        return jsonify(comparison_res), 200
    except ValueError as e:
        return jsonify({"error": "Scenario validation error", "details": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Scenario comparison failed", "details": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
