"""
FreshBasket Truck Delay Prediction Dashboard
Module 3, Lab E -- Streamlit Application

Priya's team at FreshBasket uses this dashboard to monitor predicted
delivery delays across their truck fleet operating out of Pune.

Run
---
    streamlit run app.py --server.port 8501

The app works in two modes:
  1. Live mode  -- reads features from RDS and scores with the S3 model.
  2. Demo mode  -- uses synthetic data so you can explore the UI without
                   any AWS resources.  Activated automatically when S3 or
                   RDS are unreachable, or by setting DEMO_MODE=true.
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


def _score(df, model, encoder, scaler):
    """Score a DataFrame: use the trained model if all artifacts are present,
    otherwise fall back to the heuristic predictor on the same real features.
    """
    if model is not None and encoder is not None and scaler is not None:
        return apply_prediction_pipeline(df, model, encoder, scaler)
    return apply_heuristic_predictions(df)


# ── Page configuration (must be the first Streamlit call) ────────────
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
    """Load model/encoder/scaler once and cache across reruns."""
    return load_artifacts()


@st.cache_resource(show_spinner="Connecting to database ...")
def cached_get_engine():
    """Create and cache the SQLAlchemy engine."""
    return get_db_engine()


# =====================================================================
# Sidebar
# =====================================================================

def render_sidebar(is_demo, no_trained_model=False):
    """Render the sidebar with model metadata and instructions.

    Parameters
    ----------
    is_demo : bool -- True if neither RDS nor model are available
    no_trained_model : bool -- True if RDS works but Lab D model is missing
    """
    st.sidebar.title("Model Information")

    if is_demo:
        st.sidebar.warning("**DEMO MODE** — Using synthetic data.")
        st.sidebar.markdown(
            "Connect to AWS (S3 + RDS) for live predictions. "
            "Set `DEMO_MODE=false` and update `config.py` / env vars."
        )
        st.sidebar.metric("Model", "Synthetic heuristic")
        st.sidebar.metric("F1 Score (demo)", "N/A")
    elif no_trained_model:
        st.sidebar.info("**LIVE RDS, heuristic predictions**")
        st.sidebar.markdown(
            "Real truck/route data is being read from RDS. "
            "Delay probabilities are computed by a hand-crafted scoring rule "
            "(not the XGBoost model) because Lab D hasn't been run yet."
        )
        st.sidebar.metric("Data source", "RDS PostgreSQL")
        st.sidebar.metric("Predictor", "Heuristic (no .pkl yet)")
    else:
        st.sidebar.success("**LIVE MODE** — Connected to AWS.")
        st.sidebar.metric("Model", MODEL_NAME)
        st.sidebar.metric("Algorithm", "XGBoost Classifier")
        st.sidebar.metric("F1 Score", "0.84")

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**FreshBasket Logistics, Pune**  \n"
        "Built by Priya's MLOps team  \n"
        "Module 3, Lab E"
    )


# =====================================================================
# Visualisations
# =====================================================================

def plot_delay_distribution(df):
    """Show a histogram of predicted delay probabilities.

    Parameters
    ----------
    df : pd.DataFrame -- must contain a 'delay_prob' column
    """
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
    """Show a horizontal bar chart of top feature correlations with delay.

    Uses simple absolute correlation with delay_prob as a proxy for
    feature importance (works without access to the actual model object).

    Parameters
    ----------
    df : pd.DataFrame -- scored data with 'delay_prob' column
    """
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
    """Bar chart of average delay probability per route.

    Parameters
    ----------
    df : pd.DataFrame -- must have 'route_description' and 'delay_prob'
    """
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
    """Show the scored records as a colour-coded table.

    Parameters
    ----------
    df : pd.DataFrame -- scored data with 'delay_prob' and 'delay_pred'
    """
    if df.empty:
        st.info("No records found for this filter.")
        return

    # Summary metrics row
    total = len(df)
    delayed = int(df["delay_pred"].sum())
    avg_prob = df["delay_prob"].mean()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Trips", f"{total}")
    col2.metric("Predicted Delays", f"{delayed}")
    col3.metric("Delay Rate", f"{delayed / total:.1%}")
    col4.metric("Avg Delay Prob", f"{avg_prob:.2f}")

    # Colour-coded risk column
    display_df = df.copy()
    display_df["Risk"] = display_df["delay_prob"].apply(
        lambda p: f"{get_risk_color(p)[0]} {get_risk_color(p)[1]}"
    )
    display_df["Delay %"] = (display_df["delay_prob"] * 100).round(1)

    # Select columns for display
    show_cols = [
        c for c in [
            "truck_id", "route_id", "departure_date",
            "origin_description", "destination_description",
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

def render_date_tab(engine, model, encoder, scaler, is_demo):
    """Tab 1 -- filter predictions by departure date.

    Parameters
    ----------
    engine, model, encoder, scaler -- pipeline components (may be None)
    is_demo : bool
    """
    st.subheader("Filter by Departure Date")
    # Truck Delay data spans 2019. Default to a known-good date in that range.
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
                    df = _score(df, model, encoder, scaler)
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


def render_truck_tab(engine, model, encoder, scaler, is_demo):
    """Tab 2 -- look up a specific truck by ID.

    Parameters
    ----------
    engine, model, encoder, scaler -- pipeline components (may be None)
    is_demo : bool
    """
    st.subheader("Look Up a Truck")
    # Real truck IDs in our dataset are 8-digit integers (e.g. 30312694).
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
                    df = _score(df, model, encoder, scaler)
                else:
                    st.warning("No records for this truck -- showing demo data.")
                    df = generate_demo_data(30)
                    df["truck_id"] = truck_id

            display_results_table(df)

            st.markdown("---")
            plot_feature_importance(df)


def render_route_tab(engine, model, encoder, scaler, is_demo):
    """Tab 3 -- analyse delay patterns for a route.

    Parameters
    ----------
    engine, model, encoder, scaler -- pipeline components (may be None)
    is_demo : bool
    """
    st.subheader("Analyse a Route")
    # Real route IDs are strings like 'R-ada2a391', NOT integers.
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
                    df = _score(df, model, encoder, scaler)
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

    # ── Header ───────────────────────────────────────────────────────
    st.title("🚛 FreshBasket Truck Delay Prediction Dashboard")
    st.markdown(
        "*Predict delivery delays for FreshBasket's truck fleet "
        "operating across India  --  Pune HQ*"
    )

    # ── Load artifacts & engine ──────────────────────────────────────
    # load_artifacts() returns is_demo=True if model artifacts are missing.
    # We override that: if RDS is reachable, we stay in LIVE mode and use a
    # heuristic predictor on real data. Full demo mode triggers only if BOTH
    # the DB AND the artifacts are missing (or DEMO_MODE=true explicitly).
    model, encoder, scaler, _artifacts_missing = cached_load_artifacts()

    engine = cached_get_engine()
    is_demo = DEMO_MODE or (engine is None)
    no_trained_model = _artifacts_missing or (model is None)

    # ── Banner ───────────────────────────────────────────────────────
    if is_demo:
        st.info(
            "**Demo Mode** — RDS unreachable, the dashboard is rendering "
            "synthetic data. Set DB_HOST/DB_PASSWORD env vars (see run_live.sh) "
            "or DEMO_MODE=true."
        )
    elif no_trained_model:
        st.warning(
            "**Live RDS, heuristic predictions** — model artifacts not found in "
            "S3 yet (Lab D hasn't been run). Real truck/route data is being "
            "loaded from RDS; delay probabilities come from a hand-crafted "
            "scoring rule, not the XGBoost model. Once you run Lab D and "
            "upload the .pkl files, predictions will use the trained model."
        )

    # ── Sidebar ──────────────────────────────────────────────────────
    render_sidebar(is_demo, no_trained_model=no_trained_model)

    # ── Tabs ─────────────────────────────────────────────────────────
    tab_date, tab_truck, tab_route = st.tabs([
        "📅 By Date", "🚛 By Truck ID", "🛤️ By Route ID"
    ])

    with tab_date:
        render_date_tab(engine, model, encoder, scaler, is_demo)

    with tab_truck:
        render_truck_tab(engine, model, encoder, scaler, is_demo)

    with tab_route:
        render_route_tab(engine, model, encoder, scaler, is_demo)

    # ── Footer ───────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "FreshBasket Logistics -- Truck Delay Prediction System  |  "
        "Module 3, Lab E  |  "
        "Built by Priya & Arjun, MLOps Team, Pune"
    )


# ── Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
