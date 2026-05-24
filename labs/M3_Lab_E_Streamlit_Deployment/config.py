"""
Configuration for the Truck Delay Prediction Dashboard.
FreshBasket Logistics -- Module 3, Lab E (Deployment using Streamlit)

This file centralises every connection string, feature list, and
tunable constant so that the Streamlit app, batch scorer, and utility
helpers all draw from a single source of truth.

Artifact sources (in priority order, see utils.load_artifacts):
  1. Lab D (MLOps HP Tuning) — s3://<bucket>/models/truck-delay-tuned/
     Used ONLY when tuned_metadata.json shows delta_vs_baseline > 0,
     i.e. the tuned model genuinely beat Lab C's XGBoost.
  2. Lab C (Model Training) — s3://<bucket>/models/
     XGBoost + encoder + scaler. Used when Lab D is unavailable or
     didn't beat the baseline.
  3. Heuristic fallback (utils.apply_heuristic_predictions) — used when
     no .pkl files are reachable. Students can still explore the UI.

Update these values with your actual AWS resource details before
connecting to a live environment.  When DEMO_MODE is enabled (or the
real services are unreachable), the application falls back to
synthetic data so students can explore the dashboard immediately.
"""

import os

# =====================================================================
# Database Configuration (RDS PostgreSQL)
# =====================================================================
# Defaults are placeholders — override via env vars (see run_live.sh which
# fetches DB_PASSWORD from Secrets Manager and DB_HOST from the CloudFormation
# stack outputs).
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "truck_delay_db")
DB_USER = os.getenv("DB_USER", "mlops_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")    # MUST be set via env var

# =====================================================================
# S3 Configuration — Lab C artifacts (baseline)
# =====================================================================
# Default points at the bucket created by m3_setup.yaml. Override S3_BUCKET
# via env var when the project_name in config.yaml differs.
# These three artifacts are written by Lab C (Model Training notebook).
S3_BUCKET = os.getenv("S3_BUCKET", "mlops-m3-batch-2026")
S3_MODEL_KEY = "models/xgb-truck-model.pkl"
S3_ENCODER_KEY = "models/encoder.pkl"
S3_SCALER_KEY = "models/scaler.pkl"

# =====================================================================
# S3 Configuration — Lab D artifacts (tuned, optional)
# =====================================================================
# Lab D (MLOps HP Tuning) writes here ONLY if its winner beat Lab C's
# XGBoost F1 baseline. If these objects exist AND the metadata confirms a
# positive delta, utils.load_artifacts prefers them over the Lab C set.
S3_TUNED_DIR        = "models/truck-delay-tuned/"
S3_TUNED_MODEL_KEY  = S3_TUNED_DIR + "tuned_pipeline.pkl"
S3_TUNED_META_KEY   = S3_TUNED_DIR + "tuned_metadata.json"

# =====================================================================
# MLflow Configuration
# =====================================================================
# Points at the MLflow server on the EC2. Override via env var.
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MODEL_NAME = "truck-delay-classifier"

# =====================================================================
# Feature Configuration
# =====================================================================
# These lists must match exactly what was used during training in Lab C.
CONTINUOUS_FEATURES = [
    "route_avg_temp", "route_avg_wind_speed", "route_avg_precip",
    "route_avg_humidity", "route_avg_visibility", "route_avg_pressure",
    "origin_avg_temp", "origin_avg_wind_speed", "origin_avg_precip",
    "origin_avg_humidity", "origin_avg_visibility", "origin_avg_pressure",
    "dest_avg_temp", "dest_avg_wind_speed", "dest_avg_precip",
    "dest_avg_humidity", "dest_avg_visibility", "dest_avg_pressure",
    "truck_age", "load_capacity_pounds", "mileage_mpg",
    "driver_age", "experience", "average_speed_mph",
    "avg_no_of_vehicles", "distance", "average_hours",
]

# NOTE: Lab B saves the destination column as 'dest_description' (with prefix),
# matching the 'origin_description' / 'route_description' family. We keep that
# convention here so the encoded column lookup lines up.
CATEGORICAL_FEATURES = [
    "route_description", "origin_description", "dest_description",
    "accident", "fuel_type", "gender", "driving_style", "ratings",
    "is_midnight",
]

ENCODE_COLUMNS = [
    "route_description", "origin_description", "dest_description",
    "fuel_type", "gender", "driving_style",
]

# =====================================================================
# Demo Mode
# =====================================================================
# Set DEMO_MODE=true as an env var, or let the app auto-detect when
# AWS services are unreachable.  Demo mode uses synthetic data so
# students can explore the UI without any cloud setup.
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
