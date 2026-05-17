"""
Utility functions for the Truck Delay Prediction system.
FreshBasket Logistics -- Module 3, Lab E

This module provides helpers shared by both the Streamlit dashboard
(app.py) and the batch scoring script (batch_score.py):

  - Model / artifact loading from S3 (with demo fallback)
  - Database connection via SQLAlchemy
  - Prediction pipeline (encode -> scale -> predict)
  - Synthetic demo-data generator
  - Risk colour helper
"""

import io
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
)


# =====================================================================
# S3 helpers
# =====================================================================

def load_model_from_s3(bucket, key):
    """Download and deserialise a joblib artifact from S3.

    Parameters
    ----------
    bucket : str  -- S3 bucket name
    key    : str  -- Object key inside the bucket

    Returns
    -------
    object or None -- The deserialised Python object, or None on failure.
    """
    try:
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=bucket, Key=key)
        artifact = joblib.load(io.BytesIO(response["Body"].read()))
        print(f"  Loaded: s3://{bucket}/{key}")
        return artifact
    except Exception as e:
        print(f"  WARNING: Could not load s3://{bucket}/{key} -- {e}")
        return None


def load_artifacts():
    """Load model, encoder and scaler from S3 with demo fallback.

    Returns
    -------
    tuple of (model, encoder, scaler, is_demo : bool)
        If any artifact fails to load, all three are returned as None
        and is_demo is True so callers can switch to synthetic mode.
    """
    if DEMO_MODE:
        print("[DEMO MODE] Skipping S3 -- using synthetic predictions.")
        return None, None, None, True

    print("Loading model artifacts from S3 ...")
    model = load_model_from_s3(S3_BUCKET, S3_MODEL_KEY)
    encoder = load_model_from_s3(S3_BUCKET, S3_ENCODER_KEY)
    scaler = load_model_from_s3(S3_BUCKET, S3_SCALER_KEY)

    if model is None or encoder is None or scaler is None:
        print("  One or more artifacts missing -- falling back to demo mode.")
        return None, None, None, True

    print("All artifacts loaded successfully.")
    return model, encoder, scaler, False


# =====================================================================
# Database helpers
# =====================================================================

def get_db_engine():
    """Create a SQLAlchemy engine connected to the RDS PostgreSQL instance.

    Returns
    -------
    sqlalchemy.Engine or None
    """
    try:
        url = (
            f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
            f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
        engine = create_engine(url, pool_pre_ping=True)
        # Quick connectivity test
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"  Connected to RDS: {DB_HOST}:{DB_PORT}/{DB_NAME}")
        return engine
    except Exception as e:
        print(f"  WARNING: Database connection failed -- {e}")
        return None


def fetch_predictions_data(engine, filter_type, filter_value):
    """Query RDS for prediction data based on the chosen filter.

    Parameters
    ----------
    engine       : sqlalchemy.Engine
    filter_type  : str   -- one of 'date', 'truck', 'route'
    filter_value : str   -- the value to filter on

    Returns
    -------
    pd.DataFrame or None
    """
    # Base query -- adjust table / column names to match your Lab B schema
    base_query = """
        SELECT *
        FROM truck_schedule_with_features
        WHERE 1=1
    """

    params = {}
    if filter_type == "date":
        base_query += " AND departure_date = :val"
        params["val"] = filter_value
    elif filter_type == "truck":
        base_query += " AND truck_id = :val"
        params["val"] = int(filter_value)
    elif filter_type == "route":
        base_query += " AND route_id = :val"
        params["val"] = int(filter_value)

    base_query += " ORDER BY departure_date DESC LIMIT 500"

    try:
        df = pd.read_sql(text(base_query), engine, params=params)
        return df
    except Exception as e:
        print(f"  Query error: {e}")
        return None


# =====================================================================
# Prediction pipeline
# =====================================================================

def apply_prediction_pipeline(df, model, encoder, scaler):
    """Apply the full prediction pipeline: encode -> scale -> predict.

    Parameters
    ----------
    df      : pd.DataFrame -- raw feature data
    model   : trained XGBoost (or compatible) classifier
    encoder : fitted OrdinalEncoder / LabelEncoder
    scaler  : fitted StandardScaler / MinMaxScaler

    Returns
    -------
    pd.DataFrame -- original df with 'delay_prob' and 'delay_pred' added.
    """
    result = df.copy()

    # --- Encode categorical columns ---
    encode_cols_present = [c for c in ENCODE_COLUMNS if c in result.columns]
    if encode_cols_present and encoder is not None:
        result[encode_cols_present] = encoder.transform(
            result[encode_cols_present]
        )

    # --- Build the feature matrix in training order ---
    feature_cols = CONTINUOUS_FEATURES + CATEGORICAL_FEATURES
    available = [c for c in feature_cols if c in result.columns]
    X = result[available].copy()

    # --- Scale continuous features ---
    cont_present = [c for c in CONTINUOUS_FEATURES if c in X.columns]
    if cont_present and scaler is not None:
        X[cont_present] = scaler.transform(X[cont_present])

    # --- Predict ---
    result["delay_prob"] = model.predict_proba(X)[:, 1]
    result["delay_pred"] = (result["delay_prob"] >= 0.5).astype(int)

    return result


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
    """Generate synthetic truck-delay data for demo / offline mode.

    The data looks realistic enough for dashboard exploration but is
    entirely fabricated -- no real business data is exposed.

    Parameters
    ----------
    n : int -- number of rows to generate (default 100)

    Returns
    -------
    pd.DataFrame with the same columns the real pipeline would produce,
    plus pre-computed 'delay_prob' and 'delay_pred'.
    """
    rng = np.random.default_rng(42)

    # Pick random routes
    route_indices = rng.integers(0, len(_ROUTES), size=n)
    origins = [_ROUTES[i][0] for i in route_indices]
    destinations = [_ROUTES[i][1] for i in route_indices]

    # Departure dates spread over the last 30 days
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
        "destination_description": destinations,
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
        # Weather features (route / origin / dest)
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

    # --- Synthetic delay probability (heuristic, not a real model) ---
    # Higher delay chance for: old trucks, bad weather, midnight, accidents
    base_prob = 0.25
    prob = np.full(n, base_prob)
    prob += (df["truck_age"].values / 15) * 0.15           # older = riskier
    prob += (df["route_avg_precip"].values / 15) * 0.20    # rain = riskier
    prob += df["accident"].values * 0.20                    # accident = big bump
    prob += df["is_midnight"].values * 0.10                 # midnight = riskier
    prob -= (df["experience"].values / 25) * 0.10           # experience helps
    prob = np.clip(prob + rng.normal(0, 0.05, n), 0.02, 0.98)

    df["delay_prob"] = prob.round(3)
    df["delay_pred"] = (df["delay_prob"] >= 0.5).astype(int)

    return df


# =====================================================================
# Display helper
# =====================================================================

def get_risk_color(probability):
    """Return an emoji indicator and label based on delay probability.

    Parameters
    ----------
    probability : float -- value between 0 and 1

    Returns
    -------
    tuple of (emoji : str, label : str)
    """
    if probability < 0.3:
        return "🟢", "Low Risk"
    elif probability < 0.6:
        return "🟡", "Moderate Risk"
    else:
        return "🔴", "High Risk"
