"""
Dashboard Tab — Interactive charts and KPI metrics for Cardamom data.
=====================================================================

Displays:
  • KPI cards with latest prices, quantity, and data range
  • Interactive Plotly chart (price + quantity, dual Y-axis)
  • Sidebar controls: date range, series toggles, auctioneer filter
  • Expandable data table with CSV download
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Paths ──
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "cardamom_data.db")


# ═══════════════════════════════════════════════════════════════════════
#  Data loading
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)  # Cache for 5 minutes
def _load_prices() -> pd.DataFrame | None:
    """Load all cardamom price data from SQLite."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT date_of_auction, auctioneer, total_qty_arrived, "
            "qty_sold, max_price, avg_price "
            "FROM cardamom_prices ORDER BY date_of_auction",
            conn,
        )
        conn.close()
        df["date_of_auction"] = pd.to_datetime(df["date_of_auction"])
        return df
    except Exception as exc:
        st.error(f"Error loading price data: {exc}")
        return None


# ═══════════════════════════════════════════════════════════════════════
#  Update-Now logic
# ═══════════════════════════════════════════════════════════════════════

def _run_update() -> bool:
    """Trigger an incremental scrape inside the Streamlit session."""
    try:
        from scrapers.price_scraper import auto_scrape
        return auto_scrape()
    except Exception as exc:
        st.error(f"Update failed: {exc}")
        return False


def _handle_initial_load():
    """Bootstrap the database if it's completely empty."""
    from scrapers.price_scraper import has_existing_data, run_full_scrape

    if not has_existing_data():
        st.warning("📭 No data found. Running initial data fetch …")
        with st.spinner("Scraping historical prices — this may take several minutes …"):
            ok = run_full_scrape()
        if ok:
            st.success("✅ Data loaded successfully!")
            _load_prices.clear()
            st.rerun()
        else:
            st.error("❌ Could not fetch data. Check your internet connection.")
            st.stop()


# ═══════════════════════════════════════════════════════════════════════
#  Chart builders
# ═══════════════════════════════════════════════════════════════════════

def _build_price_chart(
    df: pd.DataFrame,
    show_max: bool,
    show_avg: bool,
    show_qty: bool,
    show_markers: bool,
) -> go.Figure:
    """Create the main dual-axis price + quantity chart."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    mode = "lines+markers" if show_markers else "lines"
    m_size = 4 if show_markers else 0

    if show_max:
        fig.add_trace(
            go.Scatter(
                x=df["date_of_auction"],
                y=df["max_price"],
                name="Max Price",
                mode=mode,
                line=dict(color="#1B5E20", width=2),
                marker=dict(size=m_size),
                hovertemplate="<b>Max:</b> ₹%{y:,.2f}<extra></extra>",
            ),
            secondary_y=False,
        )

    if show_avg:
        fig.add_trace(
            go.Scatter(
                x=df["date_of_auction"],
                y=df["avg_price"],
                name="Avg Price",
                mode=mode,
                line=dict(color="#66BB6A", width=2),
                marker=dict(size=m_size),
                hovertemplate="<b>Avg:</b> ₹%{y:,.2f}<extra></extra>",
            ),
            secondary_y=False,
        )

    if show_qty:
        fig.add_trace(
            go.Scatter(
                x=df["date_of_auction"],
                y=df["total_qty_arrived"],
                name="Qty Arrived",
                mode=mode,
                line=dict(color="#FF8F00", width=2),
                marker=dict(size=m_size),
                hovertemplate="<b>Qty:</b> %{y:,.0f} Kgs<extra></extra>",
            ),
            secondary_y=True,
        )

    fig.update_layout(
        title="Cardamom Auction — Price & Quantity History",
        hovermode="x unified",
        height=550,
        template="plotly_white",
        font=dict(size=12),
        legend=dict(orientation="h", y=-0.15),
        margin=dict(l=60, r=60, t=50, b=50),
    )
    fig.update_xaxes(title_text="Date of Auction")
    fig.update_yaxes(title_text="Price (₹ / Kg)", secondary_y=False)
    fig.update_yaxes(title_text="Quantity (Kgs)", secondary_y=True)
    return fig


# ═══════════════════════════════════════════════════════════════════════
#  KPI cards
# ═══════════════════════════════════════════════════════════════════════

def _show_kpis(df: pd.DataFrame) -> None:
    """Render the KPI metric cards across 4 columns."""
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Total Records", f"{len(df):,}")
    with c2:
        st.metric(
            "Avg Price Range",
            f"₹{df['avg_price'].min():,.0f} – ₹{df['avg_price'].max():,.0f}",
        )
    with c3:
        st.metric("Total Qty (All Time)", f"{df['total_qty_arrived'].sum():,.0f} Kgs")
    with c4:
        days = (df["date_of_auction"].max() - df["date_of_auction"].min()).days
        st.metric("Data Span", f"{days:,} days")


def _show_latest_snapshot(df: pd.DataFrame) -> None:
    """Show a highlighted snapshot of the most recent auction day."""
    latest_date = df["date_of_auction"].max()
    latest = df[df["date_of_auction"] == latest_date]
    if latest.empty:
        return

    st.markdown(f"##### 🗓️ Latest Auction: **{latest_date.strftime('%d %b %Y')}**")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Max Price", f"₹{latest['max_price'].max():,.2f}")
    with c2:
        st.metric("Avg Price", f"₹{latest['avg_price'].mean():,.2f}")
    with c3:
        st.metric("Qty Arrived", f"{latest['total_qty_arrived'].sum():,.0f} Kgs")
    with c4:
        st.metric("Auctioneers", f"{latest['auctioneer'].nunique()}")


# ═══════════════════════════════════════════════════════════════════════
#  Main render function
# ═══════════════════════════════════════════════════════════════════════

def render_dashboard() -> None:
    """Entry point — called from the main app."""

    # ── Bootstrap if needed ──
    _handle_initial_load()

    # ── Load data ──
    df = _load_prices()
    if df is None or df.empty:
        st.info("No price data available yet.")
        return

    # ── Sidebar: Update Now + Controls ──
    with st.sidebar:
        st.markdown("### 🔄 Data Update")
        from scrapers.price_scraper import get_last_scraped_date, get_last_update_check
        last_date = get_last_scraped_date()
        last_check = get_last_update_check()
        st.caption(f"Latest date in DB: **{last_date or 'N/A'}**")
        st.caption(f"Last update check: **{last_check or 'Never'}**")

        if st.button("🔄 Update Now", use_container_width=True):
            with st.spinner("Scraping new data …"):
                ok = _run_update()
            if ok:
                _load_prices.clear()
                st.success("✅ Update complete!")
                st.rerun()
            else:
                st.warning("No new data found or update failed.")

        st.markdown("---")
        st.markdown("### 📋 Chart Controls")

        # Series toggles
        show_max = st.checkbox("Show Max Price", value=True)
        show_avg = st.checkbox("Show Avg Price", value=True)
        show_qty = st.checkbox("Show Qty Arrived", value=True)
        show_markers = st.checkbox("Show Markers", value=False)

        # Auctioneer filter
        auctioneers = sorted(df["auctioneer"].dropna().unique())
        if auctioneers:
            selected_aucs = st.multiselect(
                "Filter Auctioneers",
                auctioneers,
                default=auctioneers,
            )
        else:
            selected_aucs = []

        st.markdown("---")
        st.markdown("### 📅 Date Range")

        min_date = df["date_of_auction"].min().date()
        max_date = df["date_of_auction"].max().date()

        preset = st.selectbox(
            "Quick Select",
            ["All Data", "Last 3 Months", "Last 6 Months", "Last 1 Year", "Custom"],
        )

        if preset == "Last 3 Months":
            start = (pd.Timestamp.now() - timedelta(days=90)).date()
            end = max_date
        elif preset == "Last 6 Months":
            start = (pd.Timestamp.now() - timedelta(days=180)).date()
            end = max_date
        elif preset == "Last 1 Year":
            start = (pd.Timestamp.now() - timedelta(days=365)).date()
            end = max_date
        elif preset == "Custom":
            col_a, col_b = st.columns(2)
            with col_a:
                start = st.date_input("Start", value=min_date, min_value=min_date, max_value=max_date)
            with col_b:
                end = st.date_input("End", value=max_date, min_value=min_date, max_value=max_date)
        else:  # All Data
            start, end = min_date, max_date

    # ── Filter data ──
    mask = (
        (df["date_of_auction"].dt.date >= start)
        & (df["date_of_auction"].dt.date <= end)
    )
    if selected_aucs:
        mask = mask & df["auctioneer"].isin(selected_aucs)
    filtered = df[mask].copy()

    if filtered.empty:
        st.warning("No data matches the current filters.")
        return

    # ── Latest snapshot ──
    _show_latest_snapshot(df)  # always uses unfiltered latest

    st.markdown("---")

    # ── KPIs ──
    _show_kpis(filtered)

    st.markdown("---")

    # ── Chart ──
    # For charting, aggregate across auctioneers per date
    chart_df = (
        filtered.groupby("date_of_auction")
        .agg(
            max_price=("max_price", "max"),
            avg_price=("avg_price", "mean"),
            total_qty_arrived=("total_qty_arrived", "sum"),
        )
        .reset_index()
        .sort_values("date_of_auction")
    )

    fig = _build_price_chart(chart_df, show_max, show_avg, show_qty, show_markers)
    st.plotly_chart(fig, use_container_width=True)

    # ── Data table ──
    st.markdown("---")
    with st.expander("📋 View Detailed Data"):
        disp = filtered.copy()
        disp["Date"] = disp["date_of_auction"].dt.strftime("%Y-%m-%d")
        disp["Auctioneer"] = disp["auctioneer"].str.title()
        disp["Qty (Kgs)"] = disp["total_qty_arrived"].apply(lambda x: f"{x:,.0f}")
        disp["Max Price (₹/Kg)"] = disp["max_price"].apply(lambda x: f"{x:,.2f}")
        disp["Avg Price (₹/Kg)"] = disp["avg_price"].apply(lambda x: f"{x:,.2f}")

        show_cols = ["Date", "Auctioneer", "Qty (Kgs)", "Max Price (₹/Kg)", "Avg Price (₹/Kg)"]
        st.dataframe(disp[show_cols], use_container_width=True, height=400)

        csv = disp[show_cols].to_csv(index=False)
        st.download_button(
            "⬇️ Download CSV",
            data=csv,
            file_name=f"cardamom_prices_{start}_{end}.csv",
            mime="text/csv",
        )
