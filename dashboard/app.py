"""
dashboard/app.py — Streamlit monthly analytics dashboard.

Tabs
----
  1. Today's Log      — Live table of today's transactions
  2. Monthly Summary  — Bar chart of medicine volumes per vendor
  3. Vendor Mappings  — Table of all known vendor↔medicine mappings
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# ── Frozen (PyInstaller) detection ──────────────────────────────────────────
_IS_FROZEN = getattr(sys, "frozen", False)

if _IS_FROZEN:
    # When bundled, sys.executable is the binary.
    # On macOS .app: dist/MedInvoMapper.app/Contents/MacOS/MedInvoMapper
    # Data should be next to the .app -> 4 levels up.
    _EXE = Path(sys.executable)
    if _EXE.parent.name == "MacOS" and _EXE.parent.parent.name == "Contents":
        _PROJECT_ROOT = _EXE.parent.parent.parent.parent.resolve()
    else:
        _PROJECT_ROOT = _EXE.parent.resolve()
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", _PROJECT_ROOT)).resolve()
else:
    _PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    _BUNDLE_ROOT = _PROJECT_ROOT

# ── Config ────────────────────────────────────────────────────────────────────
_raw_db_url = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{_PROJECT_ROOT / 'db' / 'med_invo.db'}",
)
# Smart resolution for relative paths (sqlite:///./...)
if _raw_db_url.startswith("sqlite:///./"):
    _rel_path = _raw_db_url[len("sqlite:///./"):]
    DATABASE_URL = f"sqlite:///{_PROJECT_ROOT / _rel_path}"
else:
    DATABASE_URL = _raw_db_url

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(_PROJECT_ROOT / "outputs")))

st.set_page_config(
    page_title="Med-Invo Mapper — Dashboard",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.image("https://img.icons8.com/fluency/96/medicine.png", width=60)
st.sidebar.title("Med-Invo Mapper")
st.sidebar.markdown("**Autonomous Invoice & Label Extraction Agent**")
st.sidebar.divider()

selected_month = st.sidebar.selectbox(
    "Analytics Month",
    options=[f"{date.today().year}-{m:02d}" for m in range(1, 13)],
    index=date.today().month - 1,
)
st.sidebar.divider()
st.sidebar.caption(f"DB: `{DATABASE_URL}`")

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_resource.clear()
    st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────

st.title("💊 Medical Invoice & Label Extraction Agent")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ── KPI Cards ─────────────────────────────────────────────────────────────────

try:
    kpi_df = run_query("""
        SELECT
            COUNT(*)                                         AS total_txns,
            COUNT(DISTINCT vendor_id)                        AS unique_vendors,
            COUNT(DISTINCT medicine_id)                      AS unique_medicines,
            SUM(CASE WHEN confidence_flag='MANUAL_REVIEW'
                     THEN 1 ELSE 0 END)                      AS flagged
        FROM transactions
        WHERE DATE(timestamp) = :today
    """, {"today": date.today().isoformat()})

    row = kpi_df.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Today's Extractions", int(row["total_txns"]))
    col2.metric("Unique Vendors", int(row["unique_vendors"]))
    col3.metric("Unique Medicines", int(row["unique_medicines"]))
    col4.metric("🔴 Needs Review", int(row["flagged"]))

except Exception:
    st.warning("Database not yet initialised — run the agent to start collecting data.")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📋 Today's Log", "📊 Monthly Summary", "🗂️ Vendor Mappings"])


# ── Tab 1: Today's Log ────────────────────────────────────────────────────────

with tab1:
    st.subheader(f"Transactions for {date.today().isoformat()}")
    try:
        today_df = run_query("""
            SELECT
                t.timestamp,
                v.vendor_name,
                t.invoice_number,
                m.medicine_name,
                m.medicine_code,
                t.batch_number,
                t.manufacturing_date,
                t.expiry_date,
                t.quantity,
                t.unit,
                t.free_quantity,
                t.mrp,
                t.ptr,
                t.discount_percent,
                t.discount_amount,
                t.base_amount,
                t.gst_percent,
                t.amount,
                t.hsn_code,
                t.location,
                t.confidence_flag,
                t.source_image
            FROM transactions t
            LEFT JOIN vendors   v ON t.vendor_id   = v.id
            LEFT JOIN medicines m ON t.medicine_id = m.id
            WHERE DATE(t.timestamp) = :today
            ORDER BY t.timestamp DESC
        """, {"today": date.today().isoformat()})

        if today_df.empty:
            st.info("No transactions today yet. Drop an image into the agent's `inputs/` folder to get started.")
        else:
            def _color_flag(val: str) -> str:
                return {
                    "OK": "background-color: #C6EFCE",
                    "MANUAL_REVIEW": "background-color: #FFEB9C",
                    "RETRY": "background-color: #FFC7CE",
                }.get(val, "")

            styled = today_df.style.applymap(_color_flag, subset=["confidence_flag"])
            st.dataframe(styled, use_container_width=True, height=450)

            # Download button
            csv = today_df.to_csv(index=False).encode()
            st.download_button("⬇️ Download CSV", csv,
                               file_name=f"transactions_{date.today()}.csv",
                               mime="text/csv")
    except Exception as exc:
        st.error(f"Query failed: {exc}")


# ── Tab 2: Monthly Summary ────────────────────────────────────────────────────

with tab2:
    st.subheader(f"Monthly Summary — {selected_month}")
    try:
        monthly_df = run_query("""
            SELECT
                v.vendor_name,
                m.medicine_name,
                m.medicine_code,
                SUM(t.quantity) AS total_units,
                COUNT(*)        AS transaction_count
            FROM transactions t
            LEFT JOIN vendors   v ON t.vendor_id   = v.id
            LEFT JOIN medicines m ON t.medicine_id = m.id
            WHERE STRFTIME('%Y-%m', t.timestamp) = :month
            GROUP BY v.vendor_name, m.medicine_name, m.medicine_code
            ORDER BY total_units DESC
        """, {"month": selected_month})

        if monthly_df.empty:
            st.info(f"No transactions for {selected_month}.")
        else:
            col_a, col_b = st.columns([2, 1])
            with col_a:
                fig = px.bar(
                    monthly_df,
                    x="medicine_name",
                    y="total_units",
                    color="vendor_name",
                    barmode="group",
                    title=f"Medicine Volume by Vendor — {selected_month}",
                    labels={"medicine_name": "Medicine", "total_units": "Total Units",
                            "vendor_name": "Vendor"},
                    height=420,
                )
                fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig, use_container_width=True)

            with col_b:
                st.dataframe(monthly_df, use_container_width=True)

    except Exception as exc:
        st.error(f"Query failed: {exc}")


# ── Tab 3: Vendor Mappings (Agent Memory) ─────────────────────────────────────

with tab3:
    st.subheader("Vendor ↔ Medicine Mappings (Agent Memory)")
    try:
        mapping_df = run_query("""
            SELECT
                v.vendor_name,
                m.medicine_name,
                m.medicine_code,
                vm.first_seen,
                vm.last_seen,
                vm.occurrence_count
            FROM vendor_mappings vm
            JOIN vendors   v ON vm.vendor_id   = v.id
            JOIN medicines m ON vm.medicine_id = m.id
            ORDER BY vm.last_seen DESC
        """)

        if mapping_df.empty:
            st.info("No mappings yet. The agent builds this memory automatically as it processes documents.")
        else:
            st.dataframe(mapping_df, use_container_width=True)
            st.caption(f"Total unique vendor-medicine pairs: **{len(mapping_df)}**")
    except Exception as exc:
        st.error(f"Query failed: {exc}")
