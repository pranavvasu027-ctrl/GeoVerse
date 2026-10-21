"""
real_geo_data.py
=================
REAL, VERIFIABLE geospatial anchor data for GeoVerse AI.

These latitude/longitude values are real public coordinates for Pune
localities, Pune Metro stations, and major IT/business hubs. They are
used to compute REAL distances (haversine formula) - nothing here is
invented.

Data source basis:
- Locality centroids: OpenStreetMap / publicly known locality centers
- Pune Metro stations: Pune Metro (Maha Metro) public route information
- IT hub coordinates: publicly known locations of Hinjawadi IT Park,
  EON IT Park Kharadi, Magarpatta City

NOTE: Locality "centroid" coordinates are approximate central points
of each area (localities are not single addresses), which is standard
practice for locality-level geospatial analysis.
"""

# Real locality centroid coordinates (lat, lon)
LOCALITIES = {
    "Hinjawadi":       {"lat": 18.5908, "lon": 73.7392, "zone": "West Pune"},
    "Wakad":           {"lat": 18.5974, "lon": 73.7629, "zone": "West Pune"},
    "Baner":           {"lat": 18.5590, "lon": 73.7868, "zone": "West Pune"},
    "Balewadi":        {"lat": 18.5730, "lon": 73.7770, "zone": "West Pune"},
    "Kharadi":         {"lat": 18.5515, "lon": 73.9430, "zone": "East Pune"},
    "Hadapsar":        {"lat": 18.5089, "lon": 73.9260, "zone": "East Pune"},
    "Viman Nagar":     {"lat": 18.5679, "lon": 73.9143, "zone": "East Pune"},
    "Kothrud":         {"lat": 18.5074, "lon": 73.8077, "zone": "South-West Pune"},
    "Wagholi":         {"lat": 18.5788, "lon": 73.9807, "zone": "East Pune"},
    "Pimpri-Chinchwad":{"lat": 18.6298, "lon": 73.7997, "zone": "PCMC"},
}

# Real Pune Metro station coordinates (Purple + Aqua line, key stations)
METRO_STATIONS = {
    "Vanaz":            {"lat": 18.5023, "lon": 73.8080},
    "Civil Court":      {"lat": 18.5314, "lon": 73.8553},
    "PCMC":             {"lat": 18.6298, "lon": 73.7997},
    "Ramwadi":          {"lat": 18.5573, "lon": 73.9153},
    "Shivajinagar":     {"lat": 18.5304, "lon": 73.8478},
}

# Real major IT/business hub coordinates
IT_HUBS = {
    "Hinjawadi IT Park":  {"lat": 18.5913, "lon": 73.7389},
    "EON IT Park Kharadi": {"lat": 18.5510, "lon": 73.9397},
    "Magarpatta City":    {"lat": 18.5158, "lon": 73.9298},
}

# Real major highway reference points (approx. junction/entry coordinates)
HIGHWAYS = {
    "Mumbai-Pune Expressway (Dehu Road entry)": {"lat": 18.6547, "lon": 73.7669},
    "Pune-Solapur Highway (Hadapsar junction)": {"lat": 18.5008, "lon": 73.9350},
    "Old Mumbai-Pune Highway (Wakad)":          {"lat": 18.5985, "lon": 73.7610},
}
