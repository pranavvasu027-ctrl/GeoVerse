"""
valuation_model.py
==================
Property Valuation & Scenario Analysis Engine.
GeoVerse Model 2 — Property Valuation and Scenario Comparison.

Features:
1. End-to-end Machine Learning Pipeline (Random Forest & Feature Transformers).
2. Time-Consistent Train/Validation Split (prevents temporal data leakage).
3. Single Property Valuation Inference with 95% Prediction Intervals.
4. Multi-Scenario What-If Impact Simulator (infrastructure, renovation, market changes).
5. Explicit Data Provenance & Synthetic Calibration Labeling.
"""

import os
import sys
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Union

import numpy as np
import pandas as pd
import joblib

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

SRC_DIR = Path(__file__).parent.resolve()
MODEL2_DIR = SRC_DIR.parent
DATA_DIR = MODEL2_DIR / "data"

sys.path.insert(0, str(SRC_DIR))
from real_geo_data import LOCALITIES, METRO_STATIONS, IT_HUBS, HIGHWAYS
from data_processing import haversine_km, nearest_distance

MODEL_CHECKPOINT_PATH = DATA_DIR / "model_checkpoint.joblib"

# Regional Normalization Extents for Pune Metropolitan Region
REGIONAL_EXTENTS = {
    "distance_to_metro_km": (0.0, 7.71),
    "distance_to_it_hub_km": (0.06, 11.82),
    "commercial_density": (38.0, 90.0),
    "schools_nearby": (11.0, 30.0),
    "hospitals_nearby": (5.0, 16.0),
    "amenities_combined": (16.0, 46.0),
    "distance_to_highway_km": (0.23, 11.26)
}

NUMERIC_FEATURES = [
    "area_sqft",
    "bedrooms",
    "property_age_years",
    "distance_to_metro_km",
    "distance_to_highway_km",
    "distance_to_it_hub_km",
    "infrastructure_score",
    "commercial_density",
    "schools_nearby",
    "hospitals_nearby",
    "population_growth_pct",
    "new_projects_count"
]

CATEGORICAL_FEATURES = [
    "property_type",
    "zone"
]

VALID_PROPERTY_TYPES = ["Apartment", "Villa", "Row House"]


def compute_normalized_infra_score(
    dist_metro: float,
    dist_it: float,
    commercial: float,
    schools: float,
    hospitals: float,
    dist_highway: float
) -> float:
    """
    Computes infrastructure score [0 - 100] normalized against regional PMR extents.
    Formula:
      0.30 * inv_metro + 0.25 * inv_it + 0.20 * commercial + 0.15 * amenities + 0.10 * inv_highway
    """
    ext = REGIONAL_EXTENTS
    inv_m = 1.0 - max(0.0, min(1.0, (dist_metro - ext["distance_to_metro_km"][0]) / (ext["distance_to_metro_km"][1] - ext["distance_to_metro_km"][0])))
    inv_it = 1.0 - max(0.0, min(1.0, (dist_it - ext["distance_to_it_hub_km"][0]) / (ext["distance_to_it_hub_km"][1] - ext["distance_to_it_hub_km"][0])))
    comm = max(0.0, min(1.0, (commercial - ext["commercial_density"][0]) / (ext["commercial_density"][1] - ext["commercial_density"][0])))
    amen = max(0.0, min(1.0, (schools + hospitals - ext["amenities_combined"][0]) / (ext["amenities_combined"][1] - ext["amenities_combined"][0])))
    inv_hwy = 1.0 - max(0.0, min(1.0, (dist_highway - ext["distance_to_highway_km"][0]) / (ext["distance_to_highway_km"][1] - ext["distance_to_highway_km"][0])))

    score = (
        0.30 * inv_m +
        0.25 * inv_it +
        0.20 * comm +
        0.15 * amen +
        0.10 * inv_hwy
    ) * 100.0
    return round(float(score), 2)


class PropertyValuationModel:
    """
    Trained property valuation regressor for Pune Metropolitan Region.
    Supports prediction and what-if scenario simulations.
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or MODEL_CHECKPOINT_PATH
        self.pipeline: Optional[Pipeline] = None
        self.metrics: Dict[str, float] = {}
        self.residual_std: float = 450000.0
        self.version = "geoverse_m2_rf_v1.0"
        self._load_or_train_default()

    def _build_pipeline(self) -> Pipeline:
        preprocessor = ColumnTransformer(
            transformers=[
                ("num", StandardScaler(), NUMERIC_FEATURES),
                ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES)
            ]
        )
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=12,
            min_samples_split=4,
            random_state=42,
            n_jobs=-1
        )
        return Pipeline(steps=[("preprocessor", preprocessor), ("regressor", model)])

    def train(self, data_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Trains the valuation model using strict temporal separation:
        Train: years <= 2023
        Holdout Test: year == 2024
        Prevents future-price lookahead bias.
        """
        csv_file = data_path or (DATA_DIR / "processed" / "master_training_data.csv")
        if not csv_file.exists():
            raise FileNotFoundError(f"Training data not found at {csv_file}")

        df = pd.read_csv(csv_file)

        # Temporal split to prevent data leakage
        train_df = df[df["year_observed"] <= 2023].copy()
        test_df = df[df["year_observed"] == 2024].copy()

        if len(train_df) == 0 or len(test_df) == 0:
            train_df = df.sample(frac=0.8, random_state=42)
            test_df = df.drop(train_df.index)

        X_train = train_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
        y_train = train_df["price"]

        X_test = test_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
        y_test = test_df["price"]

        self.pipeline = self._build_pipeline()
        self.pipeline.fit(X_train, y_train)

        # Evaluation on test holdout
        y_pred = self.pipeline.predict(X_test)
        mae = float(mean_absolute_error(y_test, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        r2 = float(r2_score(y_test, y_pred))
        mape = float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100.0)

        residuals = y_test - y_pred
        self.residual_std = float(np.std(residuals))

        self.metrics = {
            "mae_inr": round(mae, 2),
            "rmse_inr": round(rmse, 2),
            "r2_score": round(r2, 4),
            "mape_pct": round(mape, 2),
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "evaluation_holdout_year": 2024
        }

        # Save checkpoint
        checkpoint = {
            "pipeline": self.pipeline,
            "metrics": self.metrics,
            "residual_std": self.residual_std,
            "version": self.version
        }
        joblib.dump(checkpoint, self.model_path)
        return self.metrics

    def _load_or_train_default(self):
        """Loads serialized checkpoint if available, otherwise fits default training dataset."""
        if self.model_path.exists():
            try:
                checkpoint = joblib.load(self.model_path)
                self.pipeline = checkpoint.get("pipeline")
                self.metrics = checkpoint.get("metrics", {})
                self.residual_std = checkpoint.get("residual_std", 450000.0)
                self.version = checkpoint.get("version", self.version)
                return
            except Exception as e:
                print(f"Failed to load checkpoint from {self.model_path}: {e}")

        # Fit model on training data
        csv_file = DATA_DIR / "processed" / "master_training_data.csv"
        if csv_file.exists():
            self.train(csv_file)

    def _prepare_property_features(self, prop: Dict[str, Any]) -> pd.DataFrame:
        """
        Validates input fields, fills real geospatial anchors from LOCALITIES,
        and constructs feature row for model inference.
        """
        # Validate area
        try:
            area = float(prop.get("area_sqft", 0))
            if area <= 0 or area > 30000:
                raise ValueError(f"area_sqft must be between 10 and 30,000 (got {area})")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid area_sqft: {e}")

        # Validate bedrooms
        try:
            bedrooms = int(prop.get("bedrooms", 2))
            if bedrooms < 1 or bedrooms > 12:
                raise ValueError(f"bedrooms must be between 1 and 12 (got {bedrooms})")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid bedrooms: {e}")

        # Validate property age
        try:
            age = int(prop.get("property_age_years", 0))
            if age < 0 or age > 100:
                raise ValueError(f"property_age_years must be >= 0 and <= 100 (got {age})")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid property_age_years: {e}")

        # Validate property type
        ptype = str(prop.get("property_type", "Apartment")).strip()
        if ptype not in VALID_PROPERTY_TYPES:
            raise ValueError(f"property_type must be one of {VALID_PROPERTY_TYPES} (got '{ptype}')")

        # Resolve locality and real geospatial indicators
        locality = prop.get("locality_name")
        lat = prop.get("latitude")
        lon = prop.get("longitude")

        if locality and locality in LOCALITIES:
            loc_data = LOCALITIES[locality]
            zone = loc_data.get("zone", "Central")
            loc_lat, loc_lon = loc_data["lat"], loc_data["lon"]
        elif lat is not None and lon is not None:
            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                raise ValueError("latitude and longitude must be valid floating-point numbers")

            dists = {name: haversine_km(lat, lon, pt["lat"], pt["lon"]) for name, pt in LOCALITIES.items()}
            locality = min(dists, key=dists.get)
            loc_data = LOCALITIES[locality]
            zone = loc_data.get("zone", "Central")
            loc_lat, loc_lon = lat, lon
        else:
            locality = "Hinjawadi"
            loc_data = LOCALITIES[locality]
            zone = loc_data.get("zone", "West")
            loc_lat, loc_lon = loc_data["lat"], loc_data["lon"]

        # Real distances or overridden
        dist_metro = prop.get("distance_to_metro_km")
        if dist_metro is None:
            dist_metro, _ = nearest_distance(loc_lat, loc_lon, METRO_STATIONS)
        else:
            dist_metro = max(0.0, float(dist_metro))

        dist_highway = prop.get("distance_to_highway_km")
        if dist_highway is None:
            dist_highway, _ = nearest_distance(loc_lat, loc_lon, HIGHWAYS)
        else:
            dist_highway = max(0.0, float(dist_highway))

        dist_it = prop.get("distance_to_it_hub_km")
        if dist_it is None:
            dist_it, _ = nearest_distance(loc_lat, loc_lon, IT_HUBS)
        else:
            dist_it = max(0.0, float(dist_it))

        commercial = float(prop.get("commercial_density", 65.0))
        schools = int(prop.get("schools_nearby", 18))
        hospitals = int(prop.get("hospitals_nearby", 9))
        pop_growth = float(prop.get("population_growth_pct", 2.8))
        new_projects = int(prop.get("new_projects_count", 4))

        # Dynamically compute infrastructure score based on regional PMR normalization
        infra = prop.get("infrastructure_score")
        if infra is None:
            infra = compute_normalized_infra_score(
                dist_metro=dist_metro,
                dist_it=dist_it,
                commercial=commercial,
                schools=schools,
                hospitals=hospitals,
                dist_highway=dist_highway
            )
        else:
            infra = max(0.0, min(100.0, float(infra)))

        feature_row = {
            "area_sqft": area,
            "bedrooms": bedrooms,
            "property_age_years": age,
            "distance_to_metro_km": dist_metro,
            "distance_to_highway_km": dist_highway,
            "distance_to_it_hub_km": dist_it,
            "infrastructure_score": infra,
            "commercial_density": commercial,
            "schools_nearby": schools,
            "hospitals_nearby": hospitals,
            "population_growth_pct": pop_growth,
            "new_projects_count": new_projects,
            "property_type": ptype,
            "zone": zone,
            "_resolved_locality": locality,
            "_resolved_lat": loc_lat,
            "_resolved_lon": loc_lon
        }
        return pd.DataFrame([feature_row])

    def predict(self, property_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predicts valuation for a single property and returns detailed analytical results.
        """
        if self.pipeline is None:
            raise RuntimeError("Model pipeline is not fitted or loaded.")

        feat_df = self._prepare_property_features(property_data)
        X_eval = feat_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]

        raw_price = float(self.pipeline.predict(X_eval)[0])
        area = float(feat_df["area_sqft"].iloc[0])
        age = int(feat_df["property_age_years"].iloc[0])
        infra_score = float(feat_df["infrastructure_score"].iloc[0])

        # Hedonic structural age adjustment: 0.6% depreciation per year of age (up to 20 yrs)
        age_factor = 1.0 - (min(age, 20) * 0.006)
        adjusted_price = raw_price * age_factor
        price_per_sqft = round(adjusted_price / area, 2)

        # 95% prediction interval (approx +/- 1.96 * residual_std)
        interval_margin = 1.96 * self.residual_std
        low_bound = max(round(adjusted_price - interval_margin, 0), round(area * 2500, 0))
        high_bound = round(adjusted_price + interval_margin, 0)

        # 1-year forward growth estimate based on infrastructure score
        annual_growth_rate = 0.04 + (infra_score / 100.0) * 0.07
        future_1yr = round(adjusted_price * (1.0 + annual_growth_rate), 0)

        return {
            "locality_name": feat_df["_resolved_locality"].iloc[0],
            "property_type": feat_df["property_type"].iloc[0],
            "area_sqft": area,
            "bedrooms": int(feat_df["bedrooms"].iloc[0]),
            "property_age_years": age,
            "estimated_valuation_inr": round(adjusted_price, 0),
            "price_per_sqft_inr": price_per_sqft,
            "prediction_interval_95": {
                "lower_bound_inr": low_bound,
                "upper_bound_inr": high_bound
            },
            "future_valuation_1yr_inr": future_1yr,
            "expected_annual_appreciation_pct": round(annual_growth_rate * 100.0, 2),
            "infrastructure_score": round(infra_score, 2),
            "distance_to_metro_km": round(float(feat_df["distance_to_metro_km"].iloc[0]), 2),
            "model_metadata": {
                "version": self.version,
                "algorithm": "RandomForestRegressor(n_estimators=100, max_depth=12)",
                "evaluation_metrics": self.metrics,
                "data_provenance": "trained_on_documented_synthetic_dataset",
                "is_synthetic_training_data": True,
                "is_real_registry_transaction": False
            }
        }

    def compare_scenarios(
        self,
        base_property: Dict[str, Any],
        scenarios: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluates what-if property scenarios against a baseline property.
        Scenarios can modify infrastructure proximity, renovations, or market conditions.
        """
        base_result = self.predict(base_property)
        base_price = base_result["estimated_valuation_inr"]

        scenario_evaluations = []
        for i, sc in enumerate(scenarios, start=1):
            name = sc.get("scenario_name", f"Scenario {i}")
            modifications = dict(sc.get("modifications", {}))

            # Build modified property dictionary
            modified_prop = dict(base_property)

            # Clamp physical constraints
            if "distance_to_metro_km" in modifications:
                modifications["distance_to_metro_km"] = max(0.0, float(modifications["distance_to_metro_km"]))
            if "distance_to_highway_km" in modifications:
                modifications["distance_to_highway_km"] = max(0.0, float(modifications["distance_to_highway_km"]))
            if "distance_to_it_hub_km" in modifications:
                modifications["distance_to_it_hub_km"] = max(0.0, float(modifications["distance_to_it_hub_km"]))
            if "property_age_years" in modifications:
                modifications["property_age_years"] = max(0, int(modifications["property_age_years"]))

            # Recompute infrastructure score if distance or commercial parameters changed
            if any(k in modifications for k in ["distance_to_metro_km", "distance_to_it_hub_km", "commercial_density", "distance_to_highway_km"]):
                dist_m = modifications.get("distance_to_metro_km", base_result["distance_to_metro_km"])
                dist_it = modifications.get("distance_to_it_hub_km", base_property.get("distance_to_it_hub_km", 3.0))
                dist_hwy = modifications.get("distance_to_highway_km", base_property.get("distance_to_highway_km", 2.0))
                comm = modifications.get("commercial_density", base_property.get("commercial_density", 65.0))
                schools = modifications.get("schools_nearby", base_property.get("schools_nearby", 18))
                hosp = modifications.get("hospitals_nearby", base_property.get("hospitals_nearby", 9))
                modifications["infrastructure_score"] = compute_normalized_infra_score(
                    dist_metro=dist_m,
                    dist_it=dist_it,
                    commercial=comm,
                    schools=schools,
                    hospitals=hosp,
                    dist_highway=dist_hwy
                )

            modified_prop.update(modifications)

            mod_result = self.predict(modified_prop)
            mod_price = mod_result["estimated_valuation_inr"]

            delta_inr = round(mod_price - base_price, 0)
            delta_pct = round((delta_inr / base_price) * 100.0, 2) if base_price > 0 else 0.0

            # Determine dominant impact driver
            primary_driver = "Baseline parameters retained"
            if "distance_to_metro_km" in modifications:
                old_m = base_property.get("distance_to_metro_km", base_result["distance_to_metro_km"])
                new_m = modifications["distance_to_metro_km"]
                primary_driver = f"Metro proximity change ({old_m} km -> {new_m} km)"
            elif "property_age_years" in modifications:
                old_age = base_property.get("property_age_years", base_result["property_age_years"])
                new_age = modifications["property_age_years"]
                primary_driver = f"Property renovation / structural age reset ({old_age} yr -> {new_age} yr)"
            elif "commercial_density" in modifications:
                primary_driver = "Commercial hub density expansion"
            elif "area_sqft" in modifications:
                primary_driver = "Built-up area expansion"

            scenario_evaluations.append({
                "scenario_name": name,
                "modifications_applied": modifications,
                "scenario_valuation_inr": mod_price,
                "scenario_price_per_sqft_inr": mod_result["price_per_sqft_inr"],
                "delta_inr": delta_inr,
                "delta_pct": delta_pct,
                "primary_driver": primary_driver,
                "infrastructure_score": mod_result["infrastructure_score"]
            })

        return {
            "baseline_property": {
                "locality_name": base_result["locality_name"],
                "property_type": base_result["property_type"],
                "area_sqft": base_result["area_sqft"],
                "baseline_valuation_inr": base_price,
                "baseline_price_per_sqft_inr": base_result["price_per_sqft_inr"]
            },
            "total_scenarios_evaluated": len(scenario_evaluations),
            "scenarios": scenario_evaluations,
            "data_provenance": "trained_on_documented_synthetic_dataset",
            "is_synthetic_training_data": True
        }
