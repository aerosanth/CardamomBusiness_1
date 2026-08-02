"""
Dashboard Tab — Interactive charts and KPI metrics for Cardamom data.
=====================================================================

Displays:
  • KPI cards with latest prices, quantity, and data range
  • Interactive stock market style charts for Price and Rainfall
  • Time frequency selection, synchronized axes, interactive zoom & pan
  • Delta values based on range selection
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
RAIN_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "ranfill_data.db")


# ═══════════════════════════════════════════════════════════════════════
#  Data loading
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=300)
def _load_rainfall() -> pd.DataFrame | None:
    """Load rainfall data from SQLite."""
    if not os.path.exists(RAIN_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(RAIN_DB_PATH)
        df = pd.read_sql_query("SELECT date, rainfall_bilinear_mm FROM rainfall_data WHERE location = 'Pooparai' ORDER BY date", conn)
        conn.close()
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as exc:
        st.error(f"Error loading rainfall data: {exc}")
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
#  Main render function
# ═══════════════════════════════════════════════════════════════════════

def render_dashboard() -> None:
    """Entry point — called from the main app."""

    # ── Bootstrap if needed ──
    _handle_initial_load()

    # ── Load data ──
    df_price = _load_prices()
    df_rain = _load_rainfall()
    
    if df_price is None or df_price.empty:
        st.info("No price data available yet.")
        return

    # ── Sidebar: Update Now + Controls ──
    with st.sidebar:
        st.markdown("### 🔄 Data Update")
        from scrapers.price_scraper import get_db_dates, get_last_update_check
        oldest_date, latest_date = get_db_dates()
        last_check = get_last_update_check()
        st.caption(f"Latest date in DB: **{latest_date or 'N/A'}**")
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
        st.markdown("### 📊 Chart Settings")
        
        freq = st.radio("Time Frequency", ["Daily", "Weekly", "Monthly"], index=2)
        sync_axes = st.toggle("Sync Chart X-Axes", value=True)
        
        st.markdown("---")
        st.markdown("### 📅 Date Range")

        min_date_price = df_price["date_of_auction"].min().date()
        max_date_price = df_price["date_of_auction"].max().date()
        
        if df_rain is not None and not df_rain.empty:
            min_date = min(min_date_price, df_rain["date"].min().date())
            max_date = max(max_date_price, df_rain["date"].max().date())
        else:
            min_date = min_date_price
            max_date = max_date_price

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
    mask_price = (df_price["date_of_auction"].dt.date >= start) & (df_price["date_of_auction"].dt.date <= end)
    filtered_price = df_price[mask_price].copy()
    
    if df_rain is not None and not df_rain.empty:
        mask_rain = (df_rain["date"].dt.date >= start) & (df_rain["date"].dt.date <= end)
        filtered_rain = df_rain[mask_rain].copy()
    else:
        filtered_rain = pd.DataFrame(columns=["date", "rainfall_bilinear_mm"])

    if filtered_price.empty:
        st.warning("No data matches the current filters.")
        return

    # ── Resample Data for Charts ──
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
    freq_code = freq_map[freq]
    
    # Calculate daily aggregate first for price, then resample to average
    daily_price = filtered_price.groupby("date_of_auction").agg(
        avg_price=("avg_price", "mean")
    )
    
    res_price = daily_price.resample(freq_code).agg(
        Price=("avg_price", "mean")
    ).dropna().reset_index()
    res_price.rename(columns={"date_of_auction": "Date"}, inplace=True)
    
    res_rain = pd.DataFrame()
    if not filtered_rain.empty:
        res_rain = filtered_rain.set_index("date").resample(freq_code).agg(
            Rainfall=("rainfall_bilinear_mm", "sum")
        ).dropna().reset_index()
        res_rain.rename(columns={"date": "Date"}, inplace=True)

    # ── Calculate Default Zoom (Last 100 points) ──
    all_dates = pd.Series(dtype='datetime64[ns]')
    if not res_price.empty:
        all_dates = pd.concat([all_dates, res_price['Date']])
    if not res_rain.empty:
        all_dates = pd.concat([all_dates, res_rain['Date']])
    
    all_dates = all_dates.drop_duplicates().sort_values()
    zoom_start = all_dates.iloc[-100] if len(all_dates) > 100 else all_dates.iloc[0]
    zoom_end = all_dates.iloc[-1]

    # ── Chart Construction ──
    if sync_axes and not res_rain.empty:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            row_heights=[0.7, 0.3], vertical_spacing=0.05,
                            subplot_titles=("Cardamom Price (Average)", "Rainfall (mm) - Pooparai"))
        
        fig.add_trace(go.Scatter(
            x=res_price['Date'], y=res_price['Price'], mode='lines+markers', name="Price", line=dict(color='#2ca02c')
        ), row=1, col=1)
        
        fig.add_trace(go.Bar(
            x=res_rain['Date'], y=res_rain['Rainfall'], name="Rainfall", marker_color="#42A5F5"
        ), row=2, col=1)
        
        fig.update_layout(height=650, hovermode="x unified", template="plotly_white", margin=dict(l=40, r=40, t=60, b=40), dragmode="select")
        fig.update_xaxes(rangeslider_visible=False, range=[zoom_start, zoom_end])
        
    else:
        # Separate Figures
        fig_price = go.Figure(data=[go.Scatter(
            x=res_price['Date'], y=res_price['Price'], mode='lines+markers', name="Price", line=dict(color='#2ca02c')
        )])
        fig_price.update_layout(title="Cardamom Price (Average)", height=450, hovermode="x unified", template="plotly_white", xaxis_rangeslider_visible=False, dragmode="select")
        fig_price.update_xaxes(range=[zoom_start, zoom_end])
        
        if not res_rain.empty:
            fig_rain = go.Figure(data=[go.Bar(
                x=res_rain['Date'], y=res_rain['Rainfall'], name="Rainfall", marker_color="#42A5F5"
            )])
            fig_rain.update_layout(title="Rainfall (mm) - Pooparai", height=300, hovermode="x unified", template="plotly_white", xaxis_rangeslider_visible=False, dragmode="select")
            fig_rain.update_xaxes(range=[zoom_start, zoom_end])

    # Render Charts and Catch Selection for Delta metrics
    st.markdown("### 📈 Interactive Charts")
    st.caption("💡 *Drag on the charts to zoom and pan. Use the tools menu to reset axes. If supported, drag a box on the X-axis to view Delta metrics below.*")
    
    selection = None
    if sync_axes and not res_rain.empty:
        try:
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun")
            pts = event.get("selection", {}).get("points", [])
            if pts:
                xs = [p["x"] for p in pts if "x" in p]
                if xs:
                    selection = [min(xs), max(xs)]
        except Exception as e:
            st.plotly_chart(fig, use_container_width=True)
    else:
        try:
            event_p = st.plotly_chart(fig_price, use_container_width=True, on_select="rerun")
            pts = event_p.get("selection", {}).get("points", [])
            if pts:
                xs = [p["x"] for p in pts if "x" in p]
                if xs:
                    selection = [min(xs), max(xs)]
            
            if not res_rain.empty:
                st.plotly_chart(fig_rain, use_container_width=True)
        except Exception:
            st.plotly_chart(fig_price, use_container_width=True)
            if not res_rain.empty:
                st.plotly_chart(fig_rain, use_container_width=True)

    # ── Delta Value Display ──
    # Calculate Delta over the entire currently filtered view, OR the selected zoom region if provided
    calc_start = start
    calc_end = end
    
    if selection and len(selection) == 2:
        calc_start = pd.to_datetime(selection[0]).date()
        calc_end = pd.to_datetime(selection[1]).date()
        st.markdown(f"#### 🔍 Delta Analysis for Selected Range: `{calc_start}` to `{calc_end}`")
    else:
        st.markdown(f"#### 🔍 Delta Analysis for Filtered Range: `{calc_start}` to `{calc_end}`")

    # Filter data for delta calculation
    p_sel = res_price[(res_price['Date'].dt.date >= calc_start) & (res_price['Date'].dt.date <= calc_end)]
    r_sel = pd.DataFrame()
    if not res_rain.empty:
        r_sel = res_rain[(res_rain['Date'].dt.date >= calc_start) & (res_rain['Date'].dt.date <= calc_end)]
        
    c1, c2 = st.columns(2)
    with c1:
        if not p_sel.empty and len(p_sel) >= 1:
            first_price = p_sel.iloc[0]['Price']
            last_price = p_sel.iloc[-1]['Price']
            delta_abs = last_price - first_price
            delta_pct = (delta_abs / first_price) * 100 if first_price else 0
            st.metric("Price Delta", f"₹{last_price:,.2f}", f"{delta_abs:+,.2f} ({delta_pct:+.2f}%)")
        else:
            st.metric("Price Delta", "N/A")
            
    with c2:
        if not r_sel.empty and len(r_sel) >= 1:
            first_rain = r_sel.iloc[0]['Rainfall']
            last_rain = r_sel.iloc[-1]['Rainfall']
            delta_abs_r = last_rain - first_rain
            delta_pct_r = (delta_abs_r / first_rain) * 100 if first_rain else 0
            st.metric("Rainfall Delta", f"{last_rain:,.2f} mm", f"{delta_abs_r:+,.2f} ({delta_pct_r:+.2f}%)")
        else:
            st.metric("Rainfall Delta", "N/A")



