# 🚀 Pune Smart Route Optimizer

An enterprise-grade, high-performance multimodal transit route optimization and navigation engine for the Pune Metropolitan Area. Built from the ground up using **pure custom C++ Data Structures** (zero external STL container dependencies for core logic), paired with a **Python Flask microservice** and an interactive **Leaflet.js geospatial dashboard**.

---

## 🌟 Key Highlights & Engineering Features

1. **Custom Data Structures (No STL Container Overhead)**:
   - `CustomVector<T>`: Dynamically resizing array with custom allocation, copy semantics, and element manipulation.
   - `CustomHashMap<K, V>`: Hash table implementing linked-list collision chaining and custom polynomial rolling hash.
   - `CustomMinHeap`: Binary min-heap priority queue specifically engineered for A* heuristic evaluation.

2. **Multimodal Graph Engine (63 Pune & PCMC Transit Nodes)**:
   - Full connectivity across **Metro (Purple & Aqua lines)**, **PMPML Bus corridors**, **Cabs**, **Auto Rickshaws**, and **Pedestrian Walkways**.
   - Dynamically loaded from runtime CSVs (`locations.csv` and `pune_map.csv`) without recompilation.

3. **Multi-Objective Optimization**:
   - 💰 **Cheapest Route**: Minimizes financial expenditure across multimodal fares.
   - ⚡ **Fastest Route**: Minimizes transit delay and transfer overhead.
   - 🍃 **Eco-Friendly Route**: Minimizes total carbon footprint emissions.
   - 🌧️ **Dynamic Weather Penalty**: Integrates live Open-Meteo API to penalize open-air transport (Autos/Buses) during rain.
   - 🚦 **Simulated Traffic Heuristics**: Clearly documented heuristic multipliers simulating peak-hour congestion (distinguished from measured sensor feeds).

4. **Doorstep / First-Mile Spatial Connector**:
   - If the traveler's GPS location is not an exact transit station, the spatial engine automatically computes a first-mile connector:
     - Distances <= 800 m: Walking leg (Rs 0 cost, 0 carbon).
     - Distances > 800 m: Feeder Auto connector.

5. **Multi-Stop Itinerary Optimization (Traveling Salesperson Problem)**:
   - Allows users to add up to 4 intermediate stops.
   - Uses the **Held-Karp Dynamic Programming algorithm with Bitmasking** (O(k^2 * 2^k)) to calculate the globally optimal order of visits.

6. **2D Spatial KD-Tree (O(log N) Snapping)**:
   - Custom KD-Tree built on latitude/longitude coordinates to snap any map click or device GPS coordinate to the nearest transit hub in microseconds.

7. **Live Navigation HUD & Simulation**:
   - Turn-by-turn simulation loop with directional compass orientation.
   - Real GPS tracking mode with computational geometry off-route deviation detection.
   - Non-intrusive **In-Place Arrival Signal Card** on the dashboard upon reaching the final destination.

---

## 📁 Project Structure

```text
models/model-3-smart-root-optimizer/
├── src/
│   ├── CustomDS.h              # Custom Vector, HashMap, and MinHeap data structures
│   ├── Graph.h                 # Graph interface, KD-Tree node, Edge & RouteResult structs
│   ├── Graph.cpp               # A* search, KD-Tree spatial lookup, Held-Karp TSP DP
│   ├── main.cpp                # Native C++ headless CLI & JSON serialization engine
│   └── accessibility.py        # Accessibility indicator & travel-time bridge to Model 2
├── data/
│   ├── locations.csv           # 63 Pune/PCMC transit nodes with GPS coordinates
│   └── pune_map.csv            # Fully connected multimodal graph edges
├── tests/
│   └── test_routing.py         # Automated pytest suite for routing and graph integrity
├── CMakeLists.txt              # CMake build configuration (references src/*.cpp)
├── Makefile                    # Cross-platform Makefile (Windows / Linux)
├── build.bat                   # Windows MinGW / GCC build script
├── build.sh                    # Linux / POSIX build script (g++ -O3)
├── Dockerfile                  # Containerized deployment specification
├── RouteOptimizer_Web.exe      # Pre-compiled Windows PE binary (-O3)
├── RouteOptimizer.exe          # Mirror binary
├── server.py                   # Flask REST microservice & live weather adapter
├── requirements.txt            # Python dependencies (Flask, gunicorn)
├── run.bat                     # One-click Windows launch script
├── locations.csv               # Runtime mirror for server & C++ binary
├── pune_map.csv                # Runtime mirror for server & C++ binary
├── GEOVERSE_COMPATIBILITY_REPORT.md # Technical compatibility & integration analysis
└── PATENT_SPECIFICATION.md     # Algorithmic patent draft
```

---

## 🛠️ Build and Compilation Instructions

### Platform Portability Note
The pre-compiled binary `RouteOptimizer_Web.exe` is a 64-bit Windows executable. To deploy on Linux/macOS environments:
- **Build with Make:** Run `make` to compile native binary `./RouteOptimizer_Web`.
- **Build with Shell Script:** Run `bash build.sh`.
- **Build with CMake:** Run `cmake -B build && cmake --build build`.
- **Build with Docker:** Run `docker build -t geoverse-model3 .`.

### Windows Recompilation:
```cmd
build.bat
```
Or with GCC directly:
```cmd
g++ -O3 -std=c++17 src/main.cpp src/Graph.cpp -I src -o RouteOptimizer_Web.exe
copy /Y RouteOptimizer_Web.exe RouteOptimizer.exe
```

### Linux / POSIX Recompilation:
```bash
bash build.sh
```
Or using Make:
```bash
make
```

### Graceful Fallback Behavior
When running without the compiled C++ binary:
1. `GET /api/health` indicates `"status": "degraded"` and `"binary_available": false`.
2. `POST /api/nearest` falls back to in-process spherical Haversine computation against `locations.csv`.
3. `POST /api/route` returns HTTP 503 with actionable compilation guidance.
4. `src/accessibility.py` provides pure-Python Haversine distance heuristics for transit access scores.

---

## 🚀 How to Run the Project

### Option 1: One-Click Launch (Windows)
Double-click `run.bat` in the root folder. It will:
1. Verify the C++ executable.
2. Start the Flask backend server on `http://127.0.0.1:5000`.
3. Automatically launch your default web browser to the dashboard.

### Option 2: Manual Terminal Launch
Ensure Python 3.8+ and GCC (g++) are installed.

1. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Web Server**:
   ```bash
   python server.py
   ```
3. Open `http://127.0.0.1:5000` in your browser.

---

## 📊 Algorithmic Complexity

| Component | Algorithm / Mechanism | Time Complexity | Space Complexity |
| :--- | :--- | :--- | :--- |
| **Pathfinding Engine** | A* with Haversine Admissible Heuristic | O((V + E) log V) | O(V) |
| **Spatial Snap** | 2D KD-Tree Partitioning | O(log V) average | O(V) |
| **Itinerary Optimizer** | Held-Karp DP with Bitmasking | O(k^2 * 2^k) | O(k * 2^k) |
| **Collision Handling** | Custom Hash Map (Separate Chaining) | O(1) average | O(V + E) |
| **Deviation Detection** | Point-to-Segment Minimum Euclidean Distance | O(P) | O(1) |

---

## 📜 Intellectual Property & Patent Draft
A complete formal patent disclosure has been documented under `PATENT_SPECIFICATION.md`, detailing the technical novelty of combining real-time spatial first-mile feeder discovery with weather-penalized multimodal routing and microsecond Held-Karp TSP itinerary scheduling on bare-metal custom data structures.
