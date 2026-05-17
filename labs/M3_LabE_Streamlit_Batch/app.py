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
    apply_prediction_pipeline,
    fetch_predictions_data,
    generate_demo_data,
    get_db_engine,
    get_risk_color,
    load_artifacts,
)


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

def render_sidebar(is_demo):
    """Render the sidebar with model metadata and instructions.

    Parameters
    ----------
    is_demo : bool -- whether the app is running in demo mode
    """
    st.sidebar.title("Model Information")

    if is_demo:
        st.sidebar.warning("**DEMO MODE** -- Using synthetic data.")
        st.sidebar.markdown(
            "Connect to AWS (S3 + RDS) for live predictions.  "
            "Set `DEMO_MODE=false` and update `config.py`."
        )
        st.sidebar.metric("Model", "Synthetic heuristic")
        st.sidebar.metric("F1 Score (demo)", "N/A")
    else:
        st.sidebar.success("**LIVE MODE** -- Connected to AWS.")
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
    selected_date = st.date_input("Select date", value=pd.Timestamp.now().date())

    if st.button("Fetch predictions (Date)", key="btn_date"):
        with st.spinner("Querying ..."):
            if is_demo:
                df = generate_demo_data(80)
                df["departure_date"] = str(selected_date)
            else:
                df = fetch_predictions_data(engine, "date", str(selected_date))
                if df is not None and not df.empty:
                    df = apply_prediction_pipeline(df, model, encoder, scaler)
                else:
                    st.warning("No records found -- showing demo data.")
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
    truck_id = st.number_input("Truck ID", min_value=1000, max_value=9999, value=1023)

    if st.button("Fetch predictions (Truck)", key="btn_truck"):
        with st.spinner("Querying ..."):
            if is_demo:
                df = generate_demo_data(30)
                df["truck_id"] = truck_id
            else:
                df = fetch_predictions_data(engine, "truck", str(truck_id))
                if df is not None and not df.empty:
                    df = apply_prediction_pipeline(df, model, encoder, scaler)
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
    route_id = st.number_input("Route ID", min_value=1, max_value=50, value=5)

    if st.button("Fetch predictions (Route)", key="btn_route"):
        with st.spinner("Querying ..."):
            if is_demo:
                df = generate_demo_data(60)
                df["route_id"] = route_id
            else:
                df = fetch_predictions_data(engine, "route", str(route_id))
                if df is not None and not df.empty:
                    df = apply_prediction_pipeline(df, model, encoder, scaler)
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
    model, encoder, scaler, is_demo = cached_load_artifacts()

    engine = None
    if not is_demo:
        engine = cached_get_engine()
        if engine is None:
            is_demo = True  # auto-fallback if DB unreachable

    # ── Demo mode banner ─────────────────────────────────────────────
    if is_demo:
        st.info(
            "**Demo Mode** -- The dashboard is running with synthetic data.  "
            "To connect to live AWS resources, update `config.py` with your "
            "RDS and S3 details and set `DEMO_MODE=false`."
        )

    # ── Sidebar ──────────────────────────────────────────────────────
    render_sidebar(is_demo)

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
