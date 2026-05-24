"""
FreshBasket Truck Delay Prediction Dashboard
Module 3, Lab E -- Deployment using Streamlit

Priya's team at FreshBasket uses this dashboard to monitor predicted
delivery delays across their truck fleet operating out of Pune.

Run
---
    streamlit run app.py --server.port 8501

The app works in three modes (priority order, auto-detected):
  1. Lab D tuned model -- loaded from s3://<bucket>/models/truck-delay-tuned/
     ONLY when its metadata confirms it beat Lab C's XGBoost baseline.
  2. Lab C XGBoost     -- loaded from s3://<bucket>/models/{xgb,encoder,scaler}.pkl
  3. Demo / heuristic  -- synthetic data and a hand-crafted scoring rule;
     used when no AWS connectivity or model artifacts are reachable.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from config import CONTINUOUS_FEATURES, DEMO_MODE, MODEL_NAME
from utils import (
    apply_heuristic_predictions,
    apply_prediction_pipeline,
    fetch_predictions_data,
    generate_demo_data,
    get_db_engine,
    get_risk_color,
    load_artifacts,
)


def _score(df, artifacts):
    """Score a DataFrame with whichever bundle was loaded (or heuristic)."""
    if artifacts is not None:
        return apply_prediction_pipeline(df, artifacts)
    return apply_heuristic_predictions(df)


# -- Page configuration (must be the first Streamlit call) ------------
st.set_page_config(
    page_title="FreshBasket -- Truck Delay Predictions",
    page_icon="🚛",
    layout="wide",
)


# =====================================================================
# Cached resource loaders (run once per session)
# =====================================================================

@st.cache_resource(show_spinner="Loading model artifacts ...")
def cached_load_artifacts():
    """Load (artifacts_bundle, is_demo) once and cache across reruns."""
    return load_artifacts()


@st.cache_resource(show_spinner="Connecting to database ...")
def cached_get_engine():
    """Create and cache the SQLAlchemy engine."""
    return get_db_engine()


# =====================================================================
# Sidebar
# =====================================================================

def render_sidebar(artifacts, is_demo, rds_unreachable):
    """Render the sidebar with model metadata + run-mode banner.

    Parameters
    ----------
    artifacts        : dict or None  -- bundle from load_artifacts()
    is_demo          : bool           -- True when no real model is loaded
    rds_unreachable  : bool           -- True when the DB engine is None
    """
    st.sidebar.title("Model Information")

    if is_demo and rds_unreachable:
        st.sidebar.warning("**DEMO MODE** -- synthetic data + heuristic predictor.")
        st.sidebar.markdown(
            "Neither RDS nor model artifacts are reachable. Set DEMO_MODE=false "
            "and update `config.py` / env vars to connect."
        )
        st.sidebar.metric("Data source", "Synthetic")
        st.sidebar.metric("Predictor",   "Heuristic rule")
    elif artifacts is None:
        st.sidebar.info("**LIVE RDS, heuristic predictions**")
        st.sidebar.markdown(
            "Real truck/route data is being read from RDS. Delay probabilities "
            "are computed by a hand-crafted scoring rule (Lab C / Lab D model "
            "artifacts not found on S3)."
        )
        st.sidebar.metric("Data source", "RDS PostgreSQL")
        st.sidebar.metric("Predictor",   "Heuristic (no .pkl)")
    elif artifacts.get("kind") == "lab_d_tuned":
        meta = artifacts.get("meta", {})
        st.sidebar.success("**LIVE -- Lab D tuned model**")
        st.sidebar.markdown(
            f"Loaded from S3. This model **beat** Lab C's XGBoost on the "
            f"held-out test set by `+{meta.get('delta_vs_baseline', 0):.4f}` F1."
        )
        st.sidebar.metric("Source",     "Lab D MLOps")
        st.sidebar.metric("Algorithm",  meta.get("winner_model", "?"))
        if isinstance(meta.get("test_f1"), (int, float)):
            st.sidebar.metric("Test F1", f"{meta['test_f1']:.4f}")
        if isinstance(meta.get("baseline_f1"), (int, float)):
            st.sidebar.metric("vs baseline",
                              f"+{meta.get('delta_vs_baseline', 0):.4f} F1")
    elif artifacts.get("kind") == "lab_c_xgboost":
        st.sidebar.success("**LIVE -- Lab C XGBoost baseline**")
        st.sidebar.markdown(
            "Loaded from S3. Lab D tuned model was either not run yet or did "
            "not beat this baseline -- staying on the Lab C XGBoost."
        )
        st.sidebar.metric("Source",     "Lab C")
        st.sidebar.metric("Algorithm",  "XGBoost Classifier")
        st.sidebar.metric("Test F1",    "0.679")
    else:
        st.sidebar.info("**LIVE -- unknown artifact bundle**")
        st.sidebar.metric("Source", str(artifacts.get("kind")))

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**FreshBasket Logistics, Pune**  \n"
        "Built by Priya's MLOps team  \n"
        "Module 3, Lab E -- Deployment using Streamlit"
    )


# =====================================================================
# Visualisations
# =====================================================================

def plot_delay_distribution(df):
    """Show a histogram of predicted delay probabilities."""
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.hist(df["delay_prob"], bins=20, color="#2563EB", edgecolor="white", alpha=0.85)
    ax.set_xlabel("Delay Probability")
    ax.set_ylabel("Number of Trips")
    ax.set_title("Distribution of Predicted Delay Probabilities")
    ax.axvline(0.5, color="#EF4444", linestyle="--", label="Threshold (0.5)")
    ax.legend()
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def plot_feature_importance(df):
    """Show a horizontal bar chart of top feature correlations with delay."""
    numeric_cols = [c for c in CONTINUOUS_FEATURES if c in df.columns]
    if not numeric_cols or "delay_prob" not in df.columns:
        st.info("Feature importance not available for this selection.")
        return

    correlations = df[numeric_cols].corrwith(df["delay_prob"]).abs().sort_values()
    top = correlations.tail(10)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(top.index, top.values, color="#2563EB", edgecolor="white")
    ax.set_xlabel("|Correlation| with Delay Probability")
    ax.set_title("Top 10 Feature Correlations")
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def plot_route_risk(df):
    """Bar chart of average delay probability per route."""
    if "route_description" not in df.columns:
        return

    route_risk = (
        df.groupby("route_description")["delay_prob"]
        .mean()
        .sort_values(ascending=False)
        .head(8)
    )

    fig, ax = plt.subplots(figsize=(6, 3))
    colours = ["#EF4444" if v >= 0.5 else "#F59E0B" if v >= 0.3 else "#22C55E"
               for v in route_risk.values]
    ax.barh(route_risk.index, route_risk.values, color=colours, edgecolor="white")
    ax.set_xlabel("Average Delay Probability")
    ax.set_title("Route-wise Delay Risk")
    ax.set_xlim(0, 1)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# =====================================================================
# Results table
# =====================================================================

def display_results_table(df):
    """Show the scored records as a colour-coded table."""
    if df.empty:
        st.info("No records found for this filter.")
        return

    total = len(df)
    delayed = int(df["delay_pred"].sum())
    avg_prob = df["delay_prob"].mean()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trips", f"{total}")
    col2.metric("Predicted Delays", f"{delayed}")
    col3.metric("Delay Rate", f"{delayed / total:.1%}")
    col4.metric("Avg Delay Prob", f"{avg_prob:.2f}")

    display_df = df.copy()
    display_df["Risk"] = display_df["delay_prob"].apply(
        lambda p: f"{get_risk_color(p)[0]} {get_risk_color(p)[1]}"
    )
    display_df["Delay %"] = (display_df["delay_prob"] * 100).round(1)

    show_cols = [
        c for c in [
            "truck_id", "route_id", "departure_date",
            "origin_description", "dest_description",
            "truck_age", "distance", "average_speed_mph",
            "Delay %", "Risk",
        ]
        if c in display_df.columns
    ]

    st.dataframe(
        display_df[show_cols].reset_index(drop=True),
        use_container_width=True,
        height=400,
    )


# =====================================================================
# Tab renderers
# =====================================================================

def render_date_tab(engine, artifacts, is_demo):
    """Tab 1 -- filter predictions by departure date."""
    st.subheader("Filter by Departure Date")
    selected_date = st.date_input(
        "Select date (truck_schedule_table spans 2019)",
        value=pd.Timestamp("2019-01-01").date(),
        min_value=pd.Timestamp("2018-12-01").date(),
        max_value=pd.Timestamp("2019-12-31").date(),
    )

    if st.button("Fetch predictions (Date)", key="btn_date"):
        with st.spinner("Querying ..."):
            if is_demo:
                df = generate_demo_data(80)
                df["departure_date"] = str(selected_date)
            else:
                df = fetch_predictions_data(engine, "date", str(selected_date))
                if df is not None and not df.empty:
                    df = _score(df, artifacts)
                else:
                    st.warning("No records found for that date -- showing demo data.")
                    df = generate_demo_data(80)
                    df["departure_date"] = str(selected_date)

            display_results_table(df)

            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                plot_delay_distribution(df)
            with c2:
                plot_route_risk(df)


def render_truck_tab(engine, artifacts, is_demo):
    """Tab 2 -- look up a specific truck by ID."""
    st.subheader("Look Up a Truck")
    truck_id = st.number_input(
        "Truck ID (e.g. 30312694)",
        min_value=10_000_000, max_value=99_999_999, value=30_312_694,
    )

    if st.button("Fetch predictions (Truck)", key="btn_truck"):
        with st.spinner("Querying ..."):
            if is_demo:
                df = generate_demo_data(30)
                df["truck_id"] = truck_id
            else:
                df = fetch_predictions_data(engine, "truck", str(truck_id))
                if df is not None and not df.empty:
                    df = _score(df, artifacts)
                else:
                    st.warning("No records for this truck -- showing demo data.")
                    df = generate_demo_data(30)
                    df["truck_id"] = truck_id

            display_results_table(df)

            st.markdown("---")
            plot_feature_importance(df)


def render_route_tab(engine, artifacts, is_demo):
    """Tab 3 -- analyse delay patterns for a route."""
    st.subheader("Analyse a Route")
    route_id = st.text_input(
        "Route ID (format: R-xxxxxxxx)",
        value="R-ada2a391",
    )

    if st.button("Fetch predictions (Route)", key="btn_route"):
        with st.spinner("Querying ..."):
            if is_demo:
                df = generate_demo_data(60)
                df["route_id"] = route_id
            else:
                df = fetch_predictions_data(engine, "route", route_id)
                if df is not None and not df.empty:
                    df = _score(df, artifacts)
                else:
                    st.warning("No records for this route -- showing demo data.")
                    df = generate_demo_data(60)
                    df["route_id"] = route_id

            display_results_table(df)

            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                plot_delay_distribution(df)
            with c2:
                plot_feature_importance(df)


# =====================================================================
# Main
# =====================================================================

def main():
    """Entry point -- assembles the full Streamlit dashboard."""

    st.title("🚛 FreshBasket Truck Delay Prediction Dashboard")
    st.markdown(
        "*Predict delivery delays for FreshBasket's truck fleet "
        "operating across India  --  Pune HQ*"
    )

    # ── Load artifacts + engine ──────────────────────────────────────
    # load_artifacts() returns (bundle, is_demo). The bundle is None when no
    # real model could be loaded, in which case _score() falls back to the
    # heuristic predictor (still using real RDS features when available).
    artifacts, _artifacts_demo = cached_load_artifacts()

    engine = cached_get_engine()
    rds_unreachable = engine is None
    is_demo = DEMO_MODE or rds_unreachable

    # ── Banner ───────────────────────────────────────────────────────
    if is_demo and artifacts is None:
        st.info(
            "**Demo Mode** -- neither RDS nor model artifacts are reachable; "
            "rendering synthetic data with a heuristic predictor."
        )
    elif rds_unreachable:
        st.warning(
            "**RDS unreachable** -- showing synthetic data. Set DB_HOST and "
            "DB_PASSWORD env vars (see `run_live.sh`) or run on the EC2 itself."
        )
    elif artifacts is None:
        st.warning(
            "**Live RDS, heuristic predictions** -- model artifacts not found on "
            "S3. Run Lab C (and optionally Lab D MLOps) to populate "
            "`models/` in your bucket."
        )
    elif artifacts.get("kind") == "lab_d_tuned":
        meta = artifacts.get("meta", {})
        st.success(
            f"**Live -- Lab D tuned model** ({meta.get('winner_model', '?')}). "
            f"Test F1 = `{meta.get('test_f1', '?')}`, beating Lab C baseline "
            f"by `+{meta.get('delta_vs_baseline', 0):.4f}`."
        )

    render_sidebar(artifacts, is_demo, rds_unreachable)

    # ── Tabs ─────────────────────────────────────────────────────────
    tab_date, tab_truck, tab_route = st.tabs([
        "📅 By Date", "🚛 By Truck ID", "🛤️ By Route ID"
    ])

    with tab_date:
        render_date_tab(engine, artifacts, is_demo)

    with tab_truck:
        render_truck_tab(engine, artifacts, is_demo)

    with tab_route:
        render_route_tab(engine, artifacts, is_demo)

    st.markdown("---")
    st.caption(
        "FreshBasket Logistics -- Truck Delay Prediction System  |  "
        "Module 3, Lab E -- Deployment using Streamlit  |  "
        "Built by Priya & Arjun, MLOps Team, Pune"
    )


if __name__ == "__main__":
    main()
