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
    # Essential features for property price ML model
    expected_cols = [
        "locality_name", "year_observed", "property_type", "area_sqft",
        "bedrooms", "price", "price_per_sqft", "future_price"
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing column {col} in master training data"
