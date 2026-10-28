from flask import Flask, render_template, request, jsonify
import subprocess
import json
import urllib.request
import random
import os
import csv
import time
import platform
import math
from pathlib import Path

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Weather Cache: Store weather response for 300 seconds (5 mins) to prevent external HTTP latency
_WEATHER_CACHE = {
    "data": None,
    "timestamp": 0.0
}
WEATHER_CACHE_TTL_SECS = 300.0


def get_locations_data():
    loc_list = []
    coords_dict = {}
    csv_path = os.path.join(BASE_DIR, 'locations.csv')
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['LocationName']
                loc_list.append(name)
                coords_dict[name] = [float(row['Latitude']), float(row['Longitude'])]
        loc_list.sort()
    except Exception as e:
        print("Error reading CSV:", e)
    return loc_list, coords_dict


def get_pune_weather():
    now = time.time()
    if _WEATHER_CACHE["data"] and (now - _WEATHER_CACHE["timestamp"]) < WEATHER_CACHE_TTL_SECS:
        return _WEATHER_CACHE["data"]

    try:
        # Open-Meteo API for Pune (Lat: 18.52, Lon: 73.85)
        url = "https://api.open-meteo.com/v1/forecast?latitude=18.52&longitude=73.85&current_weather=true"
        req = urllib.request.Request(url, headers={'User-Agent': 'GeoVerse-Model3/1.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            weather_code = data['current_weather']['weathercode']
            # WMO Weather codes: 50+ means drizzle/rain/snow/thunderstorm
            is_raining = weather_code >= 50
            weather_obj = {
                "temp": data['current_weather']['temperature'],
                "raining": is_raining,
                "description": "Raining 🌧️" if is_raining else "Clear ☀️",
                "is_fallback": False,
                "data_provenance": "open_meteo_live"
            }
            _WEATHER_CACHE["data"] = weather_obj
            _WEATHER_CACHE["timestamp"] = now
            return weather_obj
    except Exception as e:
        print("Weather API failed, using documented fallback:", e)
        fallback_obj = {
            "temp": 25.0,
            "raining": False,
            "description": "Clear ☀️",
            "is_fallback": True,
            "data_provenance": "static_fallback"
        }
        _WEATHER_CACHE["data"] = fallback_obj
        _WEATHER_CACHE["timestamp"] = now
        return fallback_obj


@app.route('/')
def index():
    weather = get_pune_weather()
    loc_list, coords_dict = get_locations_data()
    return render_template('index.html', locations=loc_list, coordinates=coords_dict, weather=weather)


@app.route('/api/route', methods=['POST'])
def get_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    src = data.get('source')
    dest = data.get('destination')
    pref = data.get('preference', 'cost')
    traffic = bool(data.get('traffic', False))
    waypoints = data.get('waypoints', [])
    optimize_tsp = bool(data.get('optimizeTSP', True))

    if not src or not dest:
        return jsonify({"error": "Missing source or destination"}), 400

    loc_list, coords_dict = get_locations_data()
    if src not in coords_dict:
        return jsonify({"error": f"Unknown source location: '{src}'"}), 400
    if dest not in coords_dict:
        return jsonify({"error": f"Unknown destination location: '{dest}'"}), 400
    if src == dest:
        return jsonify({"error": "Source and destination cannot be the same station"}), 400

    valid_preferences = ['cost', 'time', 'carbon']
    if pref not in valid_preferences:
        pref = 'cost'

    # Filter waypoints
    valid_waypoints = []
    if isinstance(waypoints, list):
        for wp in waypoints:
            if isinstance(wp, str) and wp in coords_dict and wp != src and wp != dest and wp not in valid_waypoints:
                valid_waypoints.append(wp)

    # Determine weather penalty
    weather = get_pune_weather()
    penalty = 1.0
    if weather.get('raining', False):
        penalty += 1.5  # Heavy penalty for open transport if raining

    if traffic:
        penalty += 1.0  # Simulate heavy traffic adding delay/cost penalties

    binary_file = "RouteOptimizer_Web.exe" if platform.system() == "Windows" else "RouteOptimizer_Web"
    binary_name = os.path.join(BASE_DIR, binary_file)

    if not os.path.exists(binary_name):
        return jsonify({
            "error": "C++ routing binary not found",
            "details": f"Binary '{binary_file}' not found at {binary_name}. Compile it using 'make', 'build.bat', or 'build.sh'."
        }), 503

    try:
        # Support both point-to-point and Multi-Stop Tour (TSP)
        if valid_waypoints and len(valid_waypoints) > 0:
            cmd = [
                binary_name, 'tour',
                src, dest, pref, str(penalty),
                '1' if optimize_tsp else '0',
                str(len(valid_waypoints)),
                *valid_waypoints
            ]
        else:
            cmd = [binary_name, 'route', src, dest, pref, str(penalty)]

        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        route_data = json.loads(result.stdout)

        if isinstance(route_data, dict) and "error" in route_data:
            return jsonify(route_data), 404

        # Provenance and explicit mock/simulated traffic labeling
        if traffic and 'totalTime' in route_data:
            route_data['totalTime'] = int(route_data['totalTime'] * random.uniform(1.2, 1.8))
            route_data['trafficAlert'] = True
            route_data['is_simulated_traffic'] = True
            route_data['traffic_multiplier_range'] = [1.2, 1.8]
            route_data['traffic_alert_message'] = "Simulated rush-hour traffic penalty applied (heuristic multiplier, not measured live sensor data)."
            route_data['data_provenance'] = 'c_plus_plus_dijkstra_with_simulated_traffic'
        else:
            route_data['is_simulated_traffic'] = False
            route_data['data_provenance'] = 'c_plus_plus_dijkstra_graph_engine'

        route_data['weather_context'] = {
            "temp": weather.get("temp"),
            "raining": weather.get("raining"),
            "is_fallback": weather.get("is_fallback", False),
            "data_provenance": weather.get("data_provenance", "unknown"),
            "penalty_applied": penalty
        }

        return jsonify(route_data), 200

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "C++ Engine Failed", "details": e.stderr}), 500
    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse C++ output", "output": result.stdout}), 502
    except Exception as e:
        return jsonify({"error": "Python Server Crash", "details": str(type(e).__name__) + ": " + str(e)}), 500


@app.route('/api/nearest', methods=['POST'])
def get_nearest():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    lat_raw = data.get('lat')
    lon_raw = data.get('lon')

    if lat_raw is None or lon_raw is None:
        return jsonify({"error": "Missing coordinates: 'lat' and 'lon' are required"}), 400

    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Latitude and longitude must be valid floating-point numbers"}), 400

    # Regional envelope validation for Pune Metropolitan Region
    if not (18.0 <= lat <= 19.5 and 73.0 <= lon <= 74.5):
        return jsonify({
            "error": f"Coordinates ({lat}, {lon}) are outside the Pune Metropolitan Region envelope (Lat: [18.0, 19.5], Lon: [73.0, 74.5])"
        }), 400

    binary_file = "RouteOptimizer_Web.exe" if platform.system() == "Windows" else "RouteOptimizer_Web"
    binary_name = os.path.join(BASE_DIR, binary_file)

    if not os.path.exists(binary_name):
        # Fallback to pure Python Haversine lookup if binary not compiled
        loc_list, coords_dict = get_locations_data()
        if coords_dict:
            def h_dist(lat1, lon1, lat2, lon2):
                R = 6371.0
                dlat = math.radians(lat2 - lat1)
                dlon = math.radians(lon2 - lon1)
                a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
                return 2 * R * math.asin(math.sqrt(a))
            best_loc = min(coords_dict.keys(), key=lambda k: h_dist(lat, lon, coords_dict[k][0], coords_dict[k][1]))
            return jsonify({
                "nearest": best_loc,
                "nearest_node": best_loc,
                "kdTreeTimeUs": 0.0,
                "query_coordinates": [lat, lon],
                "data_provenance": "python_haversine_fallback",
                "is_fallback": True
            }), 200
        return jsonify({
            "error": "C++ routing binary not found",
            "details": f"Binary '{binary_file}' not found at {binary_name}."
        }), 503

    try:
        result = subprocess.run(
            [binary_name, 'nearest', str(lat), str(lon)],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        data_json = json.loads(result.stdout)
        if 'nearest' in data_json and 'nearest_node' not in data_json:
            data_json['nearest_node'] = data_json['nearest']

        data_json['query_coordinates'] = [lat, lon]
        data_json['data_provenance'] = 'c_plus_plus_kdtree_spatial_index'
        return jsonify(data_json), 200
    except Exception as e:
        return jsonify({"error": "KD-Tree lookup failed", "details": str(e)}), 500


@app.route('/api/accessibility', methods=['POST'])
def get_accessibility():
    """
    Computes regional accessibility indicators from Pune multimodal transit graph.
    Bridges Model 3 transit travel times with Model 2 property valuation.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    lat_raw = data.get('lat')
    lon_raw = data.get('lon')
    loc_name = data.get('location')

    loc_list, coords_dict = get_locations_data()

    if loc_name and loc_name in coords_dict:
        lat, lon = coords_dict[loc_name]
    elif lat_raw is not None and lon_raw is not None:
        try:
            lat = float(lat_raw)
            lon = float(lon_raw)
        except (ValueError, TypeError):
            return jsonify({"error": "Latitude and longitude must be valid floating-point numbers"}), 400
        if not (18.0 <= lat <= 19.5 and 73.0 <= lon <= 74.5):
            return jsonify({"error": f"Coordinates ({lat}, {lon}) are outside Pune Metropolitan Region"}), 400
    else:
        return jsonify({"error": "Provide either 'location' name or ('lat', 'lon') coordinates"}), 400

    try:
        from src.accessibility import compute_accessibility_indicators
        acc_data = compute_accessibility_indicators(lat, lon)
        return jsonify(acc_data), 200
    except Exception as e:
        return jsonify({"error": "Failed to compute accessibility indicators", "details": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    binary_file = "RouteOptimizer_Web.exe" if platform.system() == "Windows" else "RouteOptimizer_Web"
    binary_path = os.path.join(BASE_DIR, binary_file)
    loc_list, _ = get_locations_data()
    binary_exists = os.path.exists(binary_path)
    return jsonify({
        "status": "healthy" if binary_exists else "degraded",
        "service": "GeoVerse Model 3 — Urban Accessibility & Routing",
        "binary_available": binary_exists,
        "total_nodes": len(loc_list),
        "weather_cached": _WEATHER_CACHE["data"] is not None
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
