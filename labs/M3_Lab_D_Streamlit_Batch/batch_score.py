"""
Batch Scoring Script -- Truck Delay Classification
FreshBasket Logistics -- Module 3, Lab E

Scores all unscored truck-route-date combinations and writes
predictions back to the 'predictions' table in RDS.

Usage
-----
    python batch_score.py

Demo mode
---------
If S3 or RDS are unreachable the script generates synthetic results
and prints them to the console so students can see the pipeline shape
without any AWS setup.
"""

import sys
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import text

from config import DB_NAME, DEMO_MODE
from utils import (
    apply_prediction_pipeline,
    generate_demo_data,
    get_db_engine,
    load_artifacts,
)


# =====================================================================
# Helpers
# =====================================================================

def fetch_unscored_records(engine):
    """Fetch truck-route-date rows that have not yet been scored.

    The query pulls from the main feature table and excludes any
    combinations already present in the predictions table.

    Parameters
    ----------
    engine : sqlalchemy.Engine

    Returns
    -------
    pd.DataFrame or None
    """
    query = text("""
        SELECT f.*
        FROM truck_schedule_with_features f
        LEFT JOIN predictions p
            ON  f.truck_id       = p.truck_id
            AND f.route_id       = p.route_id
            AND f.departure_date = p.departure_date
        WHERE p.truck_id IS NULL
        ORDER BY f.departure_date DESC
        LIMIT 1000
    """)

    try:
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        print(f"  ERROR fetching unscored records: {e}")
        return None


def write_predictions_to_rds(engine, df):
    """Write scored predictions to the 'predictions' table.

    Parameters
    ----------
    engine : sqlalchemy.Engine
    df     : pd.DataFrame -- must contain truck_id, route_id,
             departure_date, delay_prob, delay_pred

    Returns
    -------
    int -- number of rows written
    """
    cols_to_write = [
        "truck_id", "route_id", "departure_date",
        "delay_prob", "delay_pred",
    ]

    # Keep only the columns we need (others are features, not results)
    write_df = df[cols_to_write].copy()
    write_df["scored_at"] = datetime.now().isoformat()

    try:
        rows = write_df.to_sql(
            "predictions", engine, if_exists="append", index=False
        )
        return len(write_df)
    except Exception as e:
        print(f"  ERROR writing predictions: {e}")
        return 0


def print_summary(scored_df):
    """Print a human-readable scoring summary to the console.

    Parameters
    ----------
    scored_df : pd.DataFrame -- scored data with 'delay_prob' column
    """
    total = len(scored_df)
    delayed = int((scored_df["delay_pred"] == 1).sum())
    on_time = total - delayed
    avg_prob = scored_df["delay_prob"].mean()

    print(f"\n{'─'*50}")
    print(f"  Scoring Summary")
    print(f"{'─'*50}")
    print(f"  Total records scored : {total}")
    print(f"  Predicted on-time    : {on_time}  ({on_time/total:.1%})")
    print(f"  Predicted delayed    : {delayed}  ({delayed/total:.1%})")
    print(f"  Average delay prob   : {avg_prob:.3f}")

    # Top 5 riskiest trips
    top5 = scored_df.nlargest(5, "delay_prob")
    print(f"\n  Top 5 riskiest trips:")
    for _, row in top5.iterrows():
        truck = row.get("truck_id", "?")
        route = row.get("route_id", "?")
        prob = row["delay_prob"]
        print(f"    Truck {truck}  Route {route}  -->  {prob:.1%} delay risk")

    print(f"{'─'*50}\n")


# =====================================================================
# Main
# =====================================================================

def run_batch_scoring():
    """Execute the full batch scoring pipeline.

    Steps
    -----
    1. Load model artifacts from S3 (or enter demo mode).
    2. Connect to RDS (or enter demo mode).
    3. Fetch unscored records.
    4. Apply the prediction pipeline.
    5. Write results to the predictions table.
    6. Print summary.
    """
    print(f"\n{'='*60}")
    print(f"  FreshBasket Batch Scoring")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # ── Step 1: Load artifacts ───────────────────────────────────────
    print("[Step 1/5] Loading model artifacts ...")
    model, encoder, scaler, is_demo = load_artifacts()

    if is_demo:
        print("  Running in DEMO MODE (no AWS connection).\n")

    # ── Step 2: Connect to database ──────────────────────────────────
    engine = None
    if not is_demo:
        print("[Step 2/5] Connecting to RDS ...")
        engine = get_db_engine()
        if engine is None:
            print("  Database unreachable -- switching to demo mode.\n")
            is_demo = True

    # ── Step 3: Fetch unscored records ───────────────────────────────
    if is_demo:
        print("[Step 3/5] Generating synthetic demo data ...")
        unscored_df = generate_demo_data(n=150)
        # Remove pre-computed predictions so we can re-score
        unscored_df = unscored_df.drop(columns=["delay_prob", "delay_pred"])
        print(f"  Generated {len(unscored_df)} synthetic records.\n")
    else:
        print("[Step 3/5] Fetching unscored records from RDS ...")
        unscored_df = fetch_unscored_records(engine)
        if unscored_df is None or unscored_df.empty:
            print("  No unscored records found.  Nothing to do.")
            print(f"\n{'='*60}\n  Batch scoring complete -- 0 records.\n{'='*60}\n")
            return
        print(f"  Found {len(unscored_df)} unscored records.\n")

    # ── Step 4: Score ────────────────────────────────────────────────
    print("[Step 4/5] Applying prediction pipeline ...")
    if is_demo:
        # In demo mode we use a lightweight heuristic instead of a model
        rng = np.random.default_rng(99)
        base = 0.25
        prob = np.full(len(unscored_df), base)
        prob += (unscored_df["truck_age"].values / 15) * 0.15
        prob += (unscored_df["route_avg_precip"].values / 15) * 0.20
        prob += unscored_df["accident"].values * 0.20
        prob += unscored_df["is_midnight"].values * 0.10
        prob -= (unscored_df["experience"].values / 25) * 0.10
        prob = np.clip(prob + rng.normal(0, 0.05, len(unscored_df)), 0.02, 0.98)

        scored_df = unscored_df.copy()
        scored_df["delay_prob"] = prob.round(3)
        scored_df["delay_pred"] = (scored_df["delay_prob"] >= 0.5).astype(int)
    else:
        scored_df = apply_prediction_pipeline(unscored_df, model, encoder, scaler)

    print(f"  Scored {len(scored_df)} records.\n")

    # ── Step 5: Write results ────────────────────────────────────────
    if is_demo:
        print("[Step 5/5] DEMO MODE -- skipping database write.")
        print("  (In live mode, results would be written to the")
        print(f"   'predictions' table in {DB_NAME}.)\n")
    else:
        print("[Step 5/5] Writing predictions to RDS ...")
        written = write_predictions_to_rds(engine, scored_df)
        print(f"  Wrote {written} rows to 'predictions' table.\n")

    # ── Summary ──────────────────────────────────────────────────────
    print_summary(scored_df)

    print(f"{'='*60}")
    print(f"  Batch scoring complete.")
    print(f"{'='*60}\n")


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    run_batch_scoring()
