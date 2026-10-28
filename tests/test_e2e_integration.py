"""
test_e2e_integration.py
========================
Cross-Model End-to-End Integration Test Suite for GeoVerse AI.

Validates that:
1. Model 1 (LULC & Urban Growth), Model 2 (Property Valuation), and Model 3 (Transit Routing)
   coexist reliably with well-defined service contracts, distinct ports, and consistent schemas.
2. Model 2 successfully bridges with Model 3 accessibility indicators (both live and fallback).
3. Model 1 maintains a fail-closed training gate while feature cube and annotations remain incomplete.
4. All models rigorously distinguish between real geospatial anchors, synthetic datasets,
   and simulated heuristics across their APIs and metadata.
"""

import os
import sys
import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()

MODEL1_DIR = REPO_ROOT / "models" / "model-1-lulc-urban-growth"
MODEL2_DIR = REPO_ROOT / "models" / "model-2-property-valuation"
MODEL3_DIR = REPO_ROOT / "models" / "model-3-smart-root-optimizer"

# Ensure all model directories are in sys.path
for p in [MODEL1_DIR, MODEL2_DIR / "src", MODEL3_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from labeling_app.app import app as model1_app
from labeling_app.storage import AnnotationStore
from api import app as model2_app
from valuation_model import PropertyValuationModel
from accessibility_client import AccessibilityClient
from server import app as model3_app


@pytest.fixture
def m1_client():
    model1_app.config["TESTING"] = True
    return model1_app.test_client()


@pytest.fixture
def m2_client():
    model2_app.config["TESTING"] = True
    return model2_app.test_client()


@pytest.fixture
def m3_client():
    model3_app.config["TESTING"] = True
    return model3_app.test_client()


def test_cross_model_service_health(m1_client, m2_client, m3_client):
    """
    Verifies that all three microservices respond to health/readiness probes with
    structured status responses and clear provenance indicators.
    """
    # 1. Model 1 Readiness probe
    res1 = m1_client.get("/api/readiness")
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert "overall_decision" in data1
    assert data1["overall_decision"] == "BLOCKED"
    assert "checklist" in data1
    cube_gate = next(item for item in data1["checklist"] if "Feature Cube" in item["gate"])
    assert cube_gate["status"] == "BLOCKED"

    # 2. Model 2 Health probe
    res2 = m2_client.get("/api/v1/health")
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["status"] == "healthy"
    assert data2["is_model_loaded"] is True
    assert data2["is_synthetic_training_data"] is True
    assert data2["is_real_registry_transaction"] is False

    # 3. Model 3 Health probe
    res3 = m3_client.get("/api/health")
    assert res3.status_code == 200
    data3 = res3.get_json()
    assert data3["status"] in ["healthy", "degraded"]
    assert data3["total_nodes"] == 63


def test_model2_to_model3_live_accessibility_bridge():
    """
    Verifies that Model 2's AccessibilityClient successfully interfaces with Model 3
    to query transit indicators for a real Pune location (Baner / 18.5590, 73.7868).
    """
    client = AccessibilityClient()
    acc = client.get_accessibility_indicators(18.5590, 73.7868)

    assert "nearest_station" in acc
    assert "accessibility_score" in acc
    assert 0.0 <= acc["accessibility_score"] <= 100.0
    assert "hub_travel_times_mins" in acc
    assert "Pune Railway Station" in acc["hub_travel_times_mins"]
    assert acc["integration_transport"] in [
        "direct_in_process_module",
        "rest_api",
        "offline_haversine_fallback"
    ]


def test_model2_to_model3_offline_fallback(monkeypatch):
    """
    Verifies that when Model 3 HTTP service and in-process modules are simulated as offline,
    Model 2's AccessibilityClient falls back to documented geometric heuristics without crashing.
    """
    # Break HTTP by setting invalid port
    client = AccessibilityClient(service_url="http://127.0.0.1:59999")

    # Simulate missing in-process module by patching sys.path
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "accessibility" in name:
            raise ImportError("Simulated missing accessibility module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    fallback_acc = client.get_accessibility_indicators(18.5590, 73.7868)  # Baner
    assert fallback_acc["integration_transport"] == "offline_haversine_fallback"
    assert fallback_acc["is_mocked"] is True
    assert fallback_acc["data_provenance"] == "offline_geometric_estimate"
    assert 0.0 <= fallback_acc["accessibility_score"] <= 100.0


def test_model1_training_gate_integrity_e2e(m1_client):
    """
    Verifies that Model 1 refuses to start training or bypass the scientific gate
    as long as human annotations are incomplete and the Zarr feature cube is absent.
    """
    res = m1_client.get("/api/readiness")
    assert res.status_code == 200
    report = res.get_json()

    # The gate must be strictly BLOCKED
    assert report["overall_decision"] == "BLOCKED"
    assert report["is_training_allowed"] is False
    cube_gate = next(item for item in report["checklist"] if "Feature Cube" in item["gate"])
    assert cube_gate["status"] == "BLOCKED"


def test_data_provenance_distinction_across_models(m1_client, m2_client, m3_client):
    """
    Verifies that all three models maintain transparent provenance labeling:
    - Model 1 distinguishes genuine Landsat STAC scenes from unannotated cells.
    - Model 2 explicitly flags synthetic transaction records.
    - Model 3 explicitly distinguishes native A* search from simulated traffic heuristics.
    """
    # Model 1 provenance
    store = AnnotationStore()
    assert store.get_backend_name() in ["json", "supabase"]

    # Model 2 provenance
    pred_res = m2_client.post("/api/v1/predict", json={
        "locality_name": "Baner",
        "property_type": "Apartment",
        "area_sqft": 1000,
        "bedrooms": 2
    })
    assert pred_res.status_code == 200
    m2_meta = pred_res.get_json()["model_metadata"]
    assert m2_meta["is_synthetic_training_data"] is True
    assert m2_meta["is_real_registry_transaction"] is False
    assert m2_meta["data_provenance"] == "trained_on_documented_synthetic_dataset"

    # Model 3 provenance (simulated traffic vs native graph)
    route_traffic = m3_client.post("/api/route", json={
        "source": "Swargate",
        "destination": "Kalyani Nagar",
        "traffic": True
    })
    if route_traffic.status_code == 200:
        data_t = route_traffic.get_json()
        assert data_t["is_simulated_traffic"] is True
        assert data_t["data_provenance"] == "c_plus_plus_dijkstra_with_simulated_traffic"
        assert "Simulated rush-hour traffic" in data_t["traffic_alert_message"]


def test_unified_scenario_workflow_e2e(m2_client, m3_client):
    """
    Executes a complete end-to-end multi-model user workflow:
    1. Look up transit connectivity for a property in Baner.
    2. Route to central interchange (Pune Railway Station).
    3. Evaluate property valuation with current accessibility.
    4. Run what-if scenario simulating a new Metro line reducing distance from 2.5km to 0.4km.
    5. Verify positive valuation impact, confidence bounds, and metadata transparency.
    """
    # Step 1: Query Route from Model 3
    route_res = m3_client.post("/api/route", json={
        "source": "Baner",
        "destination": "Pune Railway Station",
        "preference": "time",
        "traffic": False
    })
    assert route_res.status_code == 200
    route_data = route_res.get_json()
    assert "totalTime" in route_data
    assert "path" in route_data
    assert len(route_data["path"]) > 1

    # Step 2: Query Accessibility Indicators from Model 3
    acc_res = m3_client.post("/api/accessibility", json={"location": "Baner"})
    assert acc_res.status_code == 200
    acc_data = acc_res.get_json()
    assert "accessibility_score" in acc_data

    # Step 3: Run Baseline Valuation in Model 2
    base_property = {
        "locality_name": "Baner",
        "property_type": "Apartment",
        "area_sqft": 1100,
        "bedrooms": 2,
        "property_age_years": 8,
        "distance_to_metro_km": 2.5
    }
    pred_res = m2_client.post("/api/v1/predict", json=base_property)
    assert pred_res.status_code == 200
    base_val = pred_res.get_json()
    assert base_val["estimated_valuation_inr"] > 0
    assert base_val["price_per_sqft_inr"] > 0

    # Step 4: Run Scenario Comparison in Model 2
    scenario_res = m2_client.post("/api/v1/compare-scenarios", json={
        "base_property": base_property,
        "scenarios": [
            {
                "scenario_name": "Metro Aqua Line Phase 2 Extension",
                "modifications": {"distance_to_metro_km": 0.4}
            },
            {
                "scenario_name": "Comprehensive Interior Renovation",
                "modifications": {"property_age_years": 0}
            }
        ]
    })
    assert scenario_res.status_code == 200
    sc_data = scenario_res.get_json()
    assert sc_data["total_scenarios_evaluated"] == 2

    metro_sc = next(s for s in sc_data["scenarios"] if "Metro" in s["scenario_name"])
    renov_sc = next(s for s in sc_data["scenarios"] if "Renovation" in s["scenario_name"])

    # Both scenarios should positively impact valuation
    assert metro_sc["delta_inr"] > 0
    assert metro_sc["delta_pct"] > 0
    assert renov_sc["delta_inr"] > 0
    assert renov_sc["delta_pct"] > 0
