"""
Utility functions for the Truck Delay Prediction system.
FreshBasket Logistics -- Module 3, Lab E (Deployment using Streamlit)

This module provides helpers shared by both the Streamlit dashboard
(app.py) and the batch scoring script (batch_score.py):

  - Model / artifact loading from S3 with three-tier priority:
        1. Lab D tuned PyCaret pipeline (if it beat Lab C's XGBoost)
        2. Lab C XGBoost + encoder + scaler (baseline)
        3. Heuristic predictor (demo fallback)
  - Database connection via SQLAlchemy
  - Unified prediction pipeline that auto-detects which artifact bundle
    was loaded and routes prediction through the right path
  - Synthetic demo-data generator
  - Risk colour helper

The "artifact bundle" returned by load_artifacts() is a dict with a 'kind'
field that downstream code uses to pick the prediction path:

  {'kind': 'lab_d_tuned', 'pipeline': <PyCaret pipeline>, 'meta': {...}}
  {'kind': 'lab_c_xgboost', 'model': ..., 'encoder': ..., 'scaler': ...}
  None  (demo / heuristic)
"""

import io
import json
from datetime import datetime, timedelta

import boto3
import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from config import (
    CATEGORICAL_FEATURES,
    CONTINUOUS_FEATURES,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    DEMO_MODE,
    ENCODE_COLUMNS,
    S3_BUCKET,
    S3_ENCODER_KEY,
    S3_MODEL_KEY,
    S3_SCALER_KEY,
    S3_TUNED_META_KEY,
    S3_TUNED_MODEL_KEY,
)


# =====================================================================
# S3 helpers
# =====================================================================

def _s3_get_bytes(bucket, key):
    """Download an object from S3 and return its bytes (or None on miss)."""
    try:
        s3 = boto3.client("s3")
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except Exception:
        return None


def _s3_load_pickle(bucket, key):
    """Download + joblib.load. Returns the object or None on any failure."""
    raw = _s3_get_bytes(bucket, key)
    if raw is None:
        return None
    try:
        return joblib.load(io.BytesIO(raw))
    except Exception as e:
        print(f"  WARNING: deserialise failed for s3://{bucket}/{key} -- {e}")
        return None


def _try_load_tuned_bundle():
    """Attempt to load the Lab D tuned PyCaret pipeline.

    Returns the bundle dict only when ALL of:
      (a) pycaret is installed in this environment (needed for predict_model)
      (b) the .pkl exists on S3
      (c) the metadata JSON exists and confirms delta_vs_baseline > 0

    Otherwise returns None and the caller falls back to Lab C. The pycaret
    check is what keeps the Docker container from crashing when no pycaret
    is in requirements.txt -- M4 documents Docker as Lab-C-only deployment;
    bare-Python on EC2 (with pycaret installed) is required for the tuned
    path. See labs/M3_Labs_D_and_E_Guide.md for the manual-promotion flow.
    """
    # Guard rail 1: PyCaret must be importable. Inside the M4 Docker image we
    # do NOT install pycaret to keep the container slim, so the tuned-model
    # path is unavailable inside Docker by design.
    try:
        import pycaret.classification  # noqa: F401
    except ImportError:
        print("  pycaret not installed in this environment -- skipping Lab D "
              "tuned path (this is expected inside the M4 Docker container; "
              "see M3_Labs_D_and_E_Guide.md for tuned-model deployment).")
        return None

    meta_raw = _s3_get_bytes(S3_BUCKET, S3_TUNED_META_KEY)
    if meta_raw is None:
        return None
    try:
        meta = json.loads(meta_raw.decode("utf-8"))
    except Exception:
        return None

    delta = meta.get("delta_vs_baseline")
    if delta is None or delta <= 0:
        print(f"  Lab D tuned model present but did not beat baseline "
              f"(delta={delta}); skipping in favour of Lab C XGBoost.")
        return None

    pipeline = _s3_load_pickle(S3_BUCKET, S3_TUNED_MODEL_KEY)
    if pipeline is None:
        return None

    print(f"  Loaded Lab D tuned pipeline ({meta.get('winner_model', '?')}) "
          f"with test F1 = {meta.get('test_f1', '?')}, "
          f"delta vs baseline = +{delta:.4f}")
    return {"kind": "lab_d_tuned", "pipeline": pipeline, "meta": meta}


def _try_load_lab_c_bundle():
    """Attempt to load the Lab C XGBoost + encoder + scaler triple."""
    model   = _s3_load_pickle(S3_BUCKET, S3_MODEL_KEY)
    encoder = _s3_load_pickle(S3_BUCKET, S3_ENCODER_KEY)
    scaler  = _s3_load_pickle(S3_BUCKET, S3_SCALER_KEY)
    if model is None or encoder is None or scaler is None:
        return None
    print("  Loaded Lab C XGBoost baseline + encoder + scaler")
    return {
        "kind":    "lab_c_xgboost",
        "model":   model,
        "encoder": encoder,
        "scaler":  scaler,
    }


def load_artifacts():
    """Load the best available model bundle, with three-tier priority.

    Priority order:
      1. Lab D tuned pipeline (if it beat Lab C's baseline F1)
      2. Lab C XGBoost + encoder + scaler
      3. None -> heuristic fallback (caller handles)

    Returns
    -------
    tuple of (artifacts_dict_or_None, is_demo : bool)
        artifacts_dict has a 'kind' field telling the caller which
        prediction path to use. is_demo is True when no real artifacts
        could be loaded.
    """
    if DEMO_MODE:
        print("[DEMO MODE] Skipping S3 -- using synthetic predictions.")
        return None, True

    print("Loading model artifacts from S3 (Lab D -> Lab C -> heuristic) ...")

    bundle = _try_load_tuned_bundle()
    if bundle is not None:
        return bundle, False

    bundle = _try_load_lab_c_bundle()
    if bundle is not None:
        return bundle, False

    print("  No artifacts loadable -- falling back to demo / heuristic mode.")
    return None, True


# =====================================================================
# Database helpers
# =====================================================================

def get_db_engine():
    """Create a SQLAlchemy engine connected to the RDS PostgreSQL instance."""
    try:
        url = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
            f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"  Connected to RDS: {DB_HOST}:{DB_PORT}/{DB_NAME}")
        return engine
    except Exception as e:
        print(f"  WARNING: Database connection failed -- {e}")
        return None


def fetch_predictions_data(engine, filter_type, filter_value):
    """Query RDS for trip-level data, joining 4 of the 7 raw tables.

    We join truck_schedule_table (the fact table) with trucks_table,
    routes_table, and drivers_table to get a useful per-trip view. Weather
    averages (which Lab B computes in the feature pipeline) are zero-filled
    here so the existing feature schema still works at inference time.
    """
    base_query = """
        SELECT
            s.truck_id,
            s.route_id,
            s.departure_date::date AS departure_date,
            s.estimated_arrival,
            s.delay AS actual_delay,
            t.truck_age,
            t.load_capacity_pounds,
            t.mileage_mpg,
            t.fuel_type,
            r.distance,
            r.average_hours,
            r.origin_id,
            r.destination_id,
            CONCAT('Route ', s.route_id)     AS route_description,
            r.origin_id                       AS origin_description,
            r.destination_id                  AS dest_description,
            d.driver_id,
            d.age          AS driver_age,
            d.experience,
            d.driving_style,
            d.gender,
            d.ratings,
            d.average_speed_mph
        FROM truck_schedule_table s
        LEFT JOIN trucks_table  t ON s.truck_id    = t.truck_id
        LEFT JOIN routes_table  r ON s.route_id    = r.route_id
        LEFT JOIN drivers_table d ON d.vehicle_no  = s.truck_id
        WHERE 1=1
    """

    params = {}
    if filter_type == "date":
        base_query += " AND s.departure_date::date = :val"
        params["val"] = filter_value
    elif filter_type == "truck":
        base_query += " AND s.truck_id = :val"
        params["val"] = int(filter_value)
    elif filter_type == "route":
        # route_id is VARCHAR (e.g. 'R-ada2a391'), not INT
        base_query += " AND s.route_id = :val"
        params["val"] = str(filter_value)

    base_query += " ORDER BY s.departure_date DESC LIMIT 500"

    try:
        df = pd.read_sql(text(base_query), engine, params=params)
        if df.empty:
            return df

        # Zero-fill the weather aggregate columns the prediction pipeline expects.
        weather_cols = [
            "route_avg_temp", "route_avg_wind_speed", "route_avg_precip",
            "route_avg_humidity", "route_avg_visibility", "route_avg_pressure",
            "origin_avg_temp", "origin_avg_wind_speed", "origin_avg_precip",
            "origin_avg_humidity", "origin_avg_visibility", "origin_avg_pressure",
            "dest_avg_temp", "dest_avg_wind_speed", "dest_avg_precip",
            "dest_avg_humidity", "dest_avg_visibility", "dest_avg_pressure",
            "avg_no_of_vehicles", "accident", "is_midnight",
        ]
        for c in weather_cols:
            if c not in df.columns:
                df[c] = 0
        return df
    except Exception as e:
        print(f"  Query error: {e}")
        return None


# =====================================================================
# Heuristic predictor -- used when no trained artifacts are available
# =====================================================================

def apply_heuristic_predictions(df):
    """Generate plausible delay probabilities from real RDS features.

    Used as a fallback when neither Lab D nor Lab C artifacts are reachable.
    Produces a delay_prob in [0, 1] based on a hand-crafted scoring function
    over truck age, distance, weather, driver experience, accident flag, etc.
    """
    if df.empty:
        return df

    result = df.copy()
    rng = np.random.default_rng(42)

    truck_age  = result.get("truck_age",        pd.Series(0, index=result.index)).fillna(0).clip(0, 30)
    experience = result.get("experience",       pd.Series(0, index=result.index)).fillna(0).clip(0, 30)
    distance   = result.get("distance",         pd.Series(0, index=result.index)).fillna(0)
    avg_hours  = result.get("average_hours",    pd.Series(0, index=result.index)).fillna(0)
    ratings    = result.get("ratings",          pd.Series(5, index=result.index)).fillna(5)
    accident   = result.get("accident",         pd.Series(0, index=result.index)).fillna(0)
    precip     = result.get("route_avg_precip", pd.Series(0, index=result.index)).fillna(0)

    prob = (
        0.20
        + (truck_age / 30) * 0.20
        - (experience / 30) * 0.15
        + (distance / 3000).clip(0, 1) * 0.10
        + (avg_hours / 50).clip(0, 1) * 0.05
        - ((ratings - 5) / 5).clip(-1, 0) * 0.05      # low ratings push prob up
        + accident.astype(float) * 0.20
        + (precip / 15).clip(0, 1) * 0.10
    )
    noise = rng.normal(0, 0.04, size=len(result))
    prob = (prob + noise).clip(0.02, 0.98)

    result["delay_prob"] = prob.round(3)
    result["delay_pred"] = (result["delay_prob"] >= 0.5).astype(int)
    return result


# =====================================================================
# Prediction pipeline (unified -- dispatches on artifacts['kind'])
# =====================================================================

def _predict_with_lab_d_tuned(df, pipeline):
    """Score with the Lab D tuned PyCaret pipeline.

    PyCaret pipelines bundle preprocessing internally, so we just hand the
    raw DataFrame in. Output columns are 'prediction_label' and
    'prediction_score' (PyCaret 3.x).
    """
    # Lazy import -- PyCaret is a heavy dependency we only need on this path.
    from pycaret.classification import predict_model

    pred_df = predict_model(pipeline, data=df, verbose=False)
    result = df.copy()
    result["delay_pred"] = pred_df["prediction_label"].astype(int).values
    if "prediction_score" in pred_df.columns:
        result["delay_prob"] = pred_df["prediction_score"].astype(float).values
    else:
        # Older PyCaret versions or models that do not expose probabilities
        result["delay_prob"] = result["delay_pred"].astype(float)
    return result


def _predict_with_lab_c_xgboost(df, model, encoder, scaler):
    """Score with the Lab C XGBoost + separate encoder + scaler."""
    result = df.copy()

    # Encode categorical columns
    encode_cols_present = [c for c in ENCODE_COLUMNS if c in result.columns]
    if encode_cols_present and encoder is not None:
        result[encode_cols_present] = encoder.transform(result[encode_cols_present])

    # Build the feature matrix in training order
    feature_cols = CONTINUOUS_FEATURES + CATEGORICAL_FEATURES
    available = [c for c in feature_cols if c in result.columns]
    X = result[available].copy()

    # Scale continuous features
    cont_present = [c for c in CONTINUOUS_FEATURES if c in X.columns]
    if cont_present and scaler is not None:
        X[cont_present] = scaler.transform(X[cont_present])

    result["delay_prob"] = model.predict_proba(X)[:, 1]
    result["delay_pred"] = (result["delay_prob"] >= 0.5).astype(int)
    return result


def apply_prediction_pipeline(df, artifacts):
    """Score df with whichever bundle was loaded.

    Parameters
    ----------
    df         : pd.DataFrame -- raw feature data
    artifacts  : dict from load_artifacts(), or None for heuristic

    Returns
    -------
    pd.DataFrame -- df with 'delay_prob' and 'delay_pred' added
    """
    if artifacts is None:
        return apply_heuristic_predictions(df)

    kind = artifacts.get("kind")
    if kind == "lab_d_tuned":
        return _predict_with_lab_d_tuned(df, artifacts["pipeline"])
    if kind == "lab_c_xgboost":
        return _predict_with_lab_c_xgboost(
            df, artifacts["model"], artifacts["encoder"], artifacts["scaler"]
        )
    print(f"  WARNING: unknown artifacts kind '{kind}' -- using heuristic.")
    return apply_heuristic_predictions(df)


# =====================================================================
# Demo-data generator
# =====================================================================

_ROUTES = [
    ("Pune", "Mumbai"), ("Delhi", "Jaipur"), ("Bengaluru", "Chennai"),
    ("Hyderabad", "Visakhapatnam"), ("Kolkata", "Patna"),
    ("Ahmedabad", "Surat"), ("Pune", "Nagpur"), ("Delhi", "Lucknow"),
]

_FUEL_TYPES = ["Diesel", "CNG", "Electric"]
_DRIVING_STYLES = ["Aggressive", "Moderate", "Conservative"]


def generate_demo_data(n=100):
    """Generate synthetic truck-delay data for demo / offline mode."""
    rng = np.random.default_rng(42)

    route_indices = rng.integers(0, len(_ROUTES), size=n)
    origins = [_ROUTES[i][0] for i in route_indices]
    destinations = [_ROUTES[i][1] for i in route_indices]

    base_date = datetime.now().date()
    dates = [
        (base_date - timedelta(days=int(d))).isoformat()
        for d in rng.integers(0, 30, size=n)
    ]

    df = pd.DataFrame({
        "truck_id": rng.integers(1001, 1051, size=n),
        "route_id": rng.integers(1, 21, size=n),
        "departure_date": dates,
        "origin_description": origins,
        "dest_description": destinations,
        "route_description": [f"{o}-{d} Highway" for o, d in zip(origins, destinations)],
        "truck_age": rng.integers(1, 16, size=n),
        "load_capacity_pounds": rng.integers(15000, 45000, size=n),
        "mileage_mpg": rng.uniform(4.0, 9.0, size=n).round(1),
        "fuel_type": rng.choice(_FUEL_TYPES, size=n),
        "driver_age": rng.integers(25, 58, size=n),
        "experience": rng.integers(1, 25, size=n),
        "driving_style": rng.choice(_DRIVING_STYLES, size=n),
        "gender": rng.choice(["Male", "Female"], size=n),
        "ratings": rng.integers(1, 6, size=n),
        "average_speed_mph": rng.uniform(30.0, 65.0, size=n).round(1),
        "distance": rng.uniform(120.0, 900.0, size=n).round(1),
        "average_hours": rng.uniform(2.0, 14.0, size=n).round(1),
        "avg_no_of_vehicles": rng.integers(100, 600, size=n),
        "accident": rng.choice([0, 1], size=n, p=[0.85, 0.15]),
        "is_midnight": rng.choice([0, 1], size=n, p=[0.75, 0.25]),
        "route_avg_temp": rng.uniform(18.0, 42.0, size=n).round(1),
        "route_avg_wind_speed": rng.uniform(2.0, 25.0, size=n).round(1),
        "route_avg_precip": rng.uniform(0.0, 15.0, size=n).round(2),
        "route_avg_humidity": rng.uniform(30.0, 95.0, size=n).round(1),
        "route_avg_visibility": rng.uniform(2.0, 10.0, size=n).round(1),
        "route_avg_pressure": rng.uniform(990.0, 1025.0, size=n).round(1),
        "origin_avg_temp": rng.uniform(18.0, 42.0, size=n).round(1),
        "origin_avg_wind_speed": rng.uniform(2.0, 25.0, size=n).round(1),
        "origin_avg_precip": rng.uniform(0.0, 15.0, size=n).round(2),
        "origin_avg_humidity": rng.uniform(30.0, 95.0, size=n).round(1),
        "origin_avg_visibility": rng.uniform(2.0, 10.0, size=n).round(1),
        "origin_avg_pressure": rng.uniform(990.0, 1025.0, size=n).round(1),
        "dest_avg_temp": rng.uniform(18.0, 42.0, size=n).round(1),
        "dest_avg_wind_speed": rng.uniform(2.0, 25.0, size=n).round(1),
        "dest_avg_precip": rng.uniform(0.0, 15.0, size=n).round(2),
        "dest_avg_humidity": rng.uniform(30.0, 95.0, size=n).round(1),
        "dest_avg_visibility": rng.uniform(2.0, 10.0, size=n).round(1),
        "dest_avg_pressure": rng.uniform(990.0, 1025.0, size=n).round(1),
    })

    base_prob = 0.25
    prob = np.full(n, base_prob)
    prob += (df["truck_age"].values / 15) * 0.15
    prob += (df["route_avg_precip"].values / 15) * 0.20
    prob += df["accident"].values * 0.20
    prob += df["is_midnight"].values * 0.10
    prob -= (df["experience"].values / 25) * 0.10
    prob = np.clip(prob + rng.normal(0, 0.05, n), 0.02, 0.98)

    df["delay_prob"] = prob.round(3)
    df["delay_pred"] = (df["delay_prob"] >= 0.5).astype(int)

    return df


# =====================================================================
# Display helper
# =====================================================================

def get_risk_color(probability):
    """Return an emoji indicator and label based on delay probability."""
    if probability < 0.3:
        return "🟢", "Low Risk"
    elif probability < 0.6:
        return "🟡", "Moderate Risk"
    else:
        return "🔴", "High Risk"
