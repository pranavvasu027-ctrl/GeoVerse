import pytest
import os
import sys
import subprocess
import json
import csv
from pathlib import Path

MODEL3_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(MODEL3_DIR))

from server import get_locations_data

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
