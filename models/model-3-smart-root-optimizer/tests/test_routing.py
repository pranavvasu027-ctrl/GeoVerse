import pytest
import os
import sys
import subprocess
import json
import csv
from pathlib import Path
from urllib.error import URLError

MODEL3_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(MODEL3_DIR))

import server
from server import get_locations_data, app


def test_locations_csv_integrity():
    csv_path = MODEL3_DIR / "locations.csv"
    assert csv_path.exists()
    loc_list, coords_dict = get_locations_data()
    assert len(loc_list) == 63, f"Expected 63 locations, got {len(loc_list)}"
    assert "Swargate" in coords_dict
    assert "Kalyani Nagar" in coords_dict
    for name, coords in coords_dict.items():
        assert 18.0 <= coords[0] <= 19.0, f"Invalid lat for {name}"
        assert 73.0 <= coords[1] <= 74.5, f"Invalid lon for {name}"


def test_pune_map_csv_integrity():
    csv_path = MODEL3_DIR / "pune_map.csv"
    assert csv_path.exists()
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) > 0
        for row in rows[:10]:
            assert "Source" in row
            assert "Destination" in row
            assert "Mode" in row
            assert float(row["Cost"]) >= 0
            assert float(row["Time"]) > 0
            assert float(row["Carbon"]) >= 0


@pytest.mark.skipif(sys.platform != "win32", reason="RouteOptimizer_Web.exe is a Windows executable")
def test_route_optimizer_binary_execution():
    exe_path = MODEL3_DIR / "RouteOptimizer_Web.exe"
    assert exe_path.exists(), "RouteOptimizer_Web.exe not found"

    cmd = [str(exe_path), "route", "Swargate", "Kalyani Nagar", "cost", "0"]
    result = subprocess.run(
        cmd,
        cwd=str(MODEL3_DIR),
        capture_output=True,
        text=True,
        check=True
    )
    data = json.loads(result.stdout)
    assert "totalCost" in data
    assert "totalTime" in data
    assert "path" in data
    assert len(data["path"]) > 1
    assert data["path"][0]["location"] == "Swargate"
    assert data["path"][-1]["location"] == "Kalyani Nagar"


# =============================================================================
# API Endpoint Integration, Input Validation & Accessibility Tests
# =============================================================================

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_route_api_input_validation(client):
    """Verifies strict input validation and appropriate HTTP 400 errors for /api/route."""
    # 1. Non-JSON / empty payload
    res = client.post("/api/route", data="not json", content_type="text/plain")
    assert res.status_code == 400
    assert "Invalid or missing JSON payload" in res.get_json()["error"]

    # 2. Missing source or destination
    res = client.post("/api/route", json={"source": "Swargate"})
    assert res.status_code == 400
    assert "Missing source or destination" in res.get_json()["error"]

    # 3. Identical source and destination
    res = client.post("/api/route", json={"source": "Swargate", "destination": "Swargate"})
    assert res.status_code == 400
    assert "Source and destination cannot be the same station" in res.get_json()["error"]

    # 4. Unknown location name
    res = client.post("/api/route", json={"source": "Atlantis", "destination": "Swargate"})
    assert res.status_code == 400
    assert "Unknown source location" in res.get_json()["error"]

    res = client.post("/api/route", json={"source": "Swargate", "destination": "Gotham City"})
    assert res.status_code == 400
    assert "Unknown destination location" in res.get_json()["error"]


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows RouteOptimizer_Web.exe binary")
def test_route_api_execution_and_provenance_labeling(client):
    """
    Verifies that routing results correctly distinguish real C++ Dijkstra calculations
    from synthetic traffic heuristics, with clear provenance metadata.
    """
    # Case A: Base routing without traffic
    res_base = client.post("/api/route", json={
        "source": "Swargate",
        "destination": "Kalyani Nagar",
        "preference": "cost",
        "traffic": False
    })
    assert res_base.status_code == 200
    data_base = res_base.get_json()
    assert "totalCost" in data_base
    assert data_base["is_simulated_traffic"] is False
    assert data_base["data_provenance"] == "c_plus_plus_dijkstra_graph_engine"

    # Case B: Routing with synthetic traffic enabled
    res_traffic = client.post("/api/route", json={
        "source": "Swargate",
        "destination": "Kalyani Nagar",
        "preference": "time",
        "traffic": True
    })
    assert res_traffic.status_code == 200
    data_traffic = res_traffic.get_json()
    assert data_traffic["is_simulated_traffic"] is True
    assert data_traffic["trafficAlert"] is True
    assert "Simulated rush-hour traffic penalty" in data_traffic["traffic_alert_message"]
    assert data_traffic["data_provenance"] == "c_plus_plus_dijkstra_with_simulated_traffic"


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows RouteOptimizer_Web.exe binary")
def test_multistop_tour_routing(client):
    """Verifies multi-stop route optimization (TSP) with intermediate waypoints."""
    res = client.post("/api/route", json={
        "source": "Swargate",
        "destination": "Kalyani Nagar",
        "waypoints": ["Shivaji Nagar", "Pune Railway Station"],
        "preference": "time",
        "optimizeTSP": True
    })
    assert res.status_code == 200
    data = res.get_json()
    assert "path" in data
    assert "orderedStops" in data
    assert len(data["orderedStops"]) >= 4
    assert data["orderedStops"][0] == "Swargate"
    assert data["orderedStops"][-1] == "Kalyani Nagar"
    assert "Shivaji Nagar" in data["orderedStops"]
    assert "Pune Railway Station" in data["orderedStops"]


def test_weather_failure_fallback(client, monkeypatch):
    """Verifies that external weather API failure does not crash routing and applies fallback."""
    # Reset cache and mock urlopen failure
    server._WEATHER_CACHE["data"] = None
    server._WEATHER_CACHE["timestamp"] = 0.0

    def mock_urlopen_fail(*args, **kwargs):
        raise URLError("Connection refused (simulated offline outage)")

    monkeypatch.setattr(server.urllib.request, "urlopen", mock_urlopen_fail)

    weather = server.get_pune_weather()
    assert weather["is_fallback"] is True
    assert weather["data_provenance"] == "static_fallback"
    assert weather["temp"] == 25.0


def test_missing_binary_route_handling(client, monkeypatch):
    """Verifies that missing C++ binary returns controlled HTTP 503 rather than crashing."""
    monkeypatch.setattr(server.os.path, "exists", lambda p: False if "RouteOptimizer" in str(p) else os.path.exists(p))

    res = client.post("/api/route", json={
        "source": "Swargate",
        "destination": "Kalyani Nagar"
    })
    assert res.status_code == 503
    data = res.get_json()
    assert "C++ routing binary not found" in data["error"]


def test_missing_binary_nearest_fallback(client, monkeypatch):
    """Verifies that missing C++ binary on /api/nearest falls back to Python Haversine calculation."""
    real_exists = os.path.exists

    def mock_exists(p):
        if "RouteOptimizer" in str(p):
            return False
        return real_exists(p)

    monkeypatch.setattr(server.os.path, "exists", mock_exists)

    res = client.post("/api/nearest", json={"lat": 18.5204, "lon": 73.8567})
    assert res.status_code == 200
    data = res.get_json()
    assert "nearest_node" in data
    assert data["is_fallback"] is True
    assert data["data_provenance"] == "python_haversine_fallback"


def test_nearest_api_input_validation(client):
    """Verifies input validation and envelope constraints for /api/nearest."""
    # 1. Missing coordinates
    res = client.post("/api/nearest", json={})
    assert res.status_code == 400
    assert "Missing coordinates" in res.get_json()["error"]

    # 2. Non-numeric coordinates
    res = client.post("/api/nearest", json={"lat": "invalid", "lon": 73.85})
    assert res.status_code == 400
    assert "floating-point numbers" in res.get_json()["error"]

    # 3. Out-of-bounds coordinates (outside Pune region)
    res = client.post("/api/nearest", json={"lat": 28.6139, "lon": 77.2090})  # New Delhi
    assert res.status_code == 400
    assert "outside the Pune Metropolitan Region envelope" in res.get_json()["error"]


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows RouteOptimizer_Web.exe binary")
def test_nearest_api_valid_coordinates(client):
    """Verifies that valid Pune coordinates resolve to the correct nearest transit station."""
    res = client.post("/api/nearest", json={"lat": 18.5204, "lon": 73.8567})
    assert res.status_code == 200
    data = res.get_json()
    assert "nearest_node" in data
    assert data["nearest_node"] in ["Shaniwar Wada", "PMC", "District Court"]
    assert data["data_provenance"] == "c_plus_plus_kdtree_spatial_index"


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows RouteOptimizer_Web.exe binary")
def test_accessibility_api_and_calculation(client):
    """Verifies accessibility endpoint and transit travel time indicators."""
    res = client.post("/api/accessibility", json={"location": "Swargate"})
    assert res.status_code == 200
    data = res.get_json()
    assert "accessibility_score" in data
    assert 0.0 <= data["accessibility_score"] <= 100.0
    assert "hub_travel_times_mins" in data
    assert "Pune Railway Station" in data["hub_travel_times_mins"]
    assert "isochrone_tier" in data
    assert data["is_mocked"] is False


def test_accessibility_api_out_of_bounds(client):
    """Verifies that out-of-bounds coordinates return 400 on /api/accessibility."""
    res = client.post("/api/accessibility", json={"lat": 12.9716, "lon": 77.5946})  # Bengaluru
    assert res.status_code == 400
    assert "outside Pune Metropolitan Region" in res.get_json()["error"]


def test_health_endpoint(client):
    """Verifies that the /api/health endpoint reports service status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["total_nodes"] == 63
