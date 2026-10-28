import pytest
import math
import sys
from pathlib import Path
import pandas as pd

# Add src to path
SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from real_geo_data import LOCALITIES, METRO_STATIONS, IT_HUBS, HIGHWAYS
from data_processing import haversine_km, nearest_distance, compute_infrastructure_score
from valuation_model import PropertyValuationModel, compute_normalized_infra_score
from api import app as model2_app
from accessibility_client import AccessibilityClient

DATA_DIR = Path(__file__).parent.parent / "data"


def test_haversine_properties():
    # Identical points
    assert haversine_km(18.5204, 73.8567, 18.5204, 73.8567) == 0.0
    # Symmetry
    d1 = haversine_km(18.5204, 73.8567, 18.5908, 73.7392)
    d2 = haversine_km(18.5908, 73.7392, 18.5204, 73.8567)
    assert abs(d1 - d2) < 1e-6
    # Plausible distance within Pune (~14-16 km between Swargate/Centre and Hinjawadi)
    assert 12.0 < d1 < 18.0


def test_geo_coordinate_bounds():
    # Pune latitude bounds: 18.3 to 18.8, longitude: 73.6 to 74.2
    for name, data in LOCALITIES.items():
        assert 18.0 <= data["lat"] <= 19.0, f"Invalid lat for {name}"
        assert 73.0 <= data["lon"] <= 74.5, f"Invalid lon for {name}"
        assert "zone" in data

    for name, data in METRO_STATIONS.items():
        assert 18.0 <= data["lat"] <= 19.0, f"Invalid lat for metro {name}"
        assert 73.0 <= data["lon"] <= 74.5, f"Invalid lon for metro {name}"

    for name, data in IT_HUBS.items():
        assert 18.0 <= data["lat"] <= 19.0, f"Invalid lat for IT hub {name}"
        assert 73.0 <= data["lon"] <= 74.5, f"Invalid lon for IT hub {name}"

    for name, data in HIGHWAYS.items():
        assert 18.0 <= data["lat"] <= 19.0, f"Invalid lat for highway {name}"
        assert 73.0 <= data["lon"] <= 74.5, f"Invalid lon for highway {name}"


def test_nearest_distance():
    # Nearest metro to Vanaz station coordinates should be Vanaz
    dist, name = nearest_distance(18.5023, 73.8080, METRO_STATIONS)
    assert name == "Vanaz"
    assert dist == 0.0


def test_infrastructure_score_calculation():
    sample_df = pd.DataFrame([{
        "locality_name": "TestLocality",
        "distance_to_metro_km": 1.0,
        "distance_to_highway_km": 2.0,
        "distance_to_it_hub_km": 3.0,
        "schools_nearby": 15,
        "hospitals_nearby": 8,
        "commercial_density": 25
    }])
    scores = compute_infrastructure_score(sample_df)
    assert len(scores) == 1
    score = scores.iloc[0]
    # Score is bounded between 0 and 100
    assert 0.0 <= score <= 100.0


def test_localities_real_csv_integrity():
    csv_path = DATA_DIR / "raw" / "localities_real.csv"
    assert csv_path.exists(), "localities_real.csv not found"
    df = pd.read_csv(csv_path)
    required_cols = [
        "locality_name", "latitude", "longitude", "zone",
        "distance_to_metro_km", "distance_to_highway_km", "distance_to_it_hub_km"
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing required column {col}"
    assert len(df) >= 10, "Expected at least 10 localities"


def test_master_training_data_schema():
    csv_path = DATA_DIR / "processed" / "master_training_data.csv"
    assert csv_path.exists(), "master_training_data.csv not found"
    df = pd.read_csv(csv_path)
    assert len(df) > 0, "master_training_data.csv is empty"
    expected_cols = [
        "locality_name", "year_observed", "property_type", "area_sqft",
        "bedrooms", "price", "price_per_sqft", "future_price"
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing column {col} in master training data"


# =============================================================================
# Valuation Model ML, Scenario Impact & API Microservice Tests
# =============================================================================

@pytest.fixture
def m2_client():
    model2_app.config["TESTING"] = True
    with model2_app.test_client() as client:
        yield client


def test_property_valuation_model_training_and_metrics():
    """Verifies that the valuation pipeline trains with time-consistent split and reaches valid metrics."""
    model = PropertyValuationModel()
    assert model.pipeline is not None
    assert "r2_score" in model.metrics
    assert model.metrics["r2_score"] > 0.65
    assert model.metrics["evaluation_holdout_year"] == 2024
    assert model.metrics["train_samples"] > 0
    assert model.metrics["test_samples"] > 0


def test_property_valuation_prediction_and_provenance():
    """Verifies single property valuation, 95% prediction intervals, and synthetic data provenance labeling."""
    model = PropertyValuationModel()
    pred = model.predict({
        "locality_name": "Baner",
        "property_type": "Apartment",
        "area_sqft": 1000,
        "bedrooms": 2,
        "property_age_years": 5
    })
    assert pred["estimated_valuation_inr"] > 0
    assert pred["price_per_sqft_inr"] > 0
    assert pred["prediction_interval_95"]["lower_bound_inr"] < pred["estimated_valuation_inr"]
    assert pred["prediction_interval_95"]["upper_bound_inr"] > pred["estimated_valuation_inr"]
    assert pred["future_valuation_1yr_inr"] > pred["estimated_valuation_inr"]
    assert pred["model_metadata"]["is_synthetic_training_data"] is True
    assert pred["model_metadata"]["is_real_registry_transaction"] is False
    assert pred["model_metadata"]["data_provenance"] == "trained_on_documented_synthetic_dataset"


def test_property_valuation_input_validation():
    """Verifies that invalid property inputs raise informative ValueErrors."""
    model = PropertyValuationModel()
    # 1. Invalid negative or zero area
    with pytest.raises(ValueError) as exc:
        model.predict({"locality_name": "Baner", "area_sqft": -100})
    assert "area_sqft must be between" in str(exc.value)

    # 2. Invalid property type
    with pytest.raises(ValueError) as exc2:
        model.predict({"locality_name": "Baner", "area_sqft": 1000, "property_type": "Castle"})
    assert "property_type must be one of" in str(exc2.value)

    # 3. Invalid bedrooms
    with pytest.raises(ValueError) as exc3:
        model.predict({"locality_name": "Baner", "area_sqft": 1000, "bedrooms": 0})
    assert "bedrooms must be between" in str(exc3.value)


def test_scenario_comparison_what_if_analysis():
    """Verifies what-if scenario comparison across infrastructure, renovation, and area expansion."""
    model = PropertyValuationModel()
    base = {
        "locality_name": "Wakad",
        "property_type": "Apartment",
        "area_sqft": 1000,
        "bedrooms": 2,
        "property_age_years": 10,
        "distance_to_metro_km": 3.5
    }
    scenarios = [
        {"scenario_name": "Metro Extension Added", "modifications": {"distance_to_metro_km": 0.3}},
        {"scenario_name": "Renovation / Structural Reset", "modifications": {"property_age_years": 0}},
        {"scenario_name": "Area Expansion to 1400 sqft", "modifications": {"area_sqft": 1400, "bedrooms": 3}}
    ]
    res = model.compare_scenarios(base, scenarios)
    assert res["total_scenarios_evaluated"] == 3
    sc_list = res["scenarios"]

    # Renovation resets age -> valuation increases
    renov_sc = next(s for s in sc_list if s["scenario_name"] == "Renovation / Structural Reset")
    assert renov_sc["delta_inr"] > 0
    assert renov_sc["delta_pct"] > 0
    assert "renovation" in renov_sc["primary_driver"].lower()

    # Area expansion -> valuation increases substantially
    area_sc = next(s for s in sc_list if s["scenario_name"] == "Area Expansion to 1400 sqft")
    assert area_sc["delta_inr"] > 1000000
    assert area_sc["delta_pct"] > 25.0


def test_model2_api_endpoints(m2_client):
    """Verifies all REST API endpoints for Model 2 microservice."""
    # 1. Health
    res_h = m2_client.get("/api/v1/health")
    assert res_h.status_code == 200
    data_h = res_h.get_json()
    assert data_h["status"] == "healthy"
    assert data_h["is_model_loaded"] is True

    # 2. Localities
    res_loc = m2_client.get("/api/v1/localities")
    assert res_loc.status_code == 200
    data_loc = res_loc.get_json()
    assert data_loc["total_localities"] >= 10

    # 3. Predict endpoint
    res_p = m2_client.post("/api/v1/predict", json={
        "locality_name": "Hinjawadi",
        "property_type": "Apartment",
        "area_sqft": 950,
        "bedrooms": 2
    })
    assert res_p.status_code == 200
    data_p = res_p.get_json()
    assert "estimated_valuation_inr" in data_p

    # 4. Predict validation failure
    res_err = m2_client.post("/api/v1/predict", json={"locality_name": "Hinjawadi", "area_sqft": -50})
    assert res_err.status_code == 400
    assert "Input validation error" in res_err.get_json()["error"]

    # 5. Compare scenarios endpoint
    res_sc = m2_client.post("/api/v1/compare-scenarios", json={
        "base_property": {
            "locality_name": "Baner",
            "property_type": "Apartment",
            "area_sqft": 1000,
            "bedrooms": 2
        },
        "scenarios": [
            {"scenario_name": "Renovation", "modifications": {"property_age_years": 0}}
        ]
    })
    assert res_sc.status_code == 200
    data_sc = res_sc.get_json()
    assert data_sc["total_scenarios_evaluated"] == 1


def test_accessibility_client_integration():
    """Verifies that Model 2 successfully interfaces with Model 3 accessibility engine."""
    client = AccessibilityClient()
    res = client.get_accessibility_indicators(18.5204, 73.8567)
    assert "nearest_station" in res
    assert "accessibility_score" in res
    assert 0.0 <= res["accessibility_score"] <= 100.0
    assert "hub_travel_times_mins" in res
    assert res["integration_transport"] in ["direct_in_process_module", "rest_api", "offline_haversine_fallback"]
