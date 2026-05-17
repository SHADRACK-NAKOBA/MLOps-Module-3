"""
Configuration for the Truck Delay Prediction Dashboard.
FreshBasket Logistics -- Module 3, Lab E

This file centralises every connection string, feature list, and
tunable constant so that the Streamlit app, batch scorer, and utility
helpers all draw from a single source of truth.

Update these values with your actual AWS resource details before
connecting to a live environment.  When DEMO_MODE is enabled (or the
real services are unreachable), the application falls back to
synthetic data so students can explore the dashboard immediately.
"""

import os

# =====================================================================
# Database Configuration (RDS PostgreSQL)
# =====================================================================
# These map to the RDS instance you created in Lab B.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "truck_delay_db")
DB_USER = os.getenv("DB_USER", "mlops_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password_here")

# =====================================================================
# S3 Configuration
# =====================================================================
# Bucket and keys where Lab D saved the trained model artifacts.
S3_BUCKET = os.getenv("S3_BUCKET", "mlops-truck-delay-demo-2026")
S3_MODEL_KEY = "models/xgb-truck-model.pkl"
S3_ENCODER_KEY = "models/encoder.pkl"
S3_SCALER_KEY = "models/scaler.pkl"

# =====================================================================
# MLflow Configuration
# =====================================================================
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

CATEGORICAL_FEATURES = [
    "route_description", "origin_description", "destination_description",
    "accident", "fuel_type", "gender", "driving_style", "ratings",
    "is_midnight",
]

ENCODE_COLUMNS = [
    "route_description", "origin_description", "destination_description",
    "fuel_type", "gender", "driving_style",
]

# =====================================================================
# Demo Mode
# =====================================================================
# Set DEMO_MODE=true as an env var, or let the app auto-detect when
# AWS services are unreachable.  Demo mode uses synthetic data so
# students can explore the UI without any cloud setup.
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
