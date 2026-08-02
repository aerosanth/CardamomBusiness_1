"""
About Tab — App information, tech stack, and update status.
============================================================
"""

from __future__ import annotations

import os
from datetime import datetime

import streamlit as st


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "cardamom_data.db")


def _db_file_modified() -> str:
    """Return the last-modified timestamp of the database file."""
    if os.path.exists(DB_PATH):
        mtime = os.path.getmtime(DB_PATH)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    return "N/A"


def render_about() -> None:
    """Entry point — called from the main app."""

    st.markdown(
        """
        ## 🌿 Cardamom Business Intelligence

        A comprehensive data platform for Indian Cardamom market analysis,
        combining **real-time auction data**, **document intelligence**, and an
        **AI-powered chatbot** — all in one place.
        """
    )

    st.markdown("---")

    # ── Features ──
    st.markdown("### ✨ Features")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
            #### 📊 Dashboard
            - Interactive price & quantity charts
            - Dual Y-axis visualization
            - Date range filters & presets
            - Auctioneer-level detail
            - CSV data export
            """
        )

    with c2:
        st.markdown(
            """
            #### 📚 Knowledge Base
            - Upload PDF, DOCX, XLSX, images
            - Scrape content from web URLs
            - AI-powered document chunking
            - Multimodal embedding (text + images)
            - RAG chatbot with source citations
            """
        )

    with c3:
        st.markdown(
            """
            #### 🤖 AI Chatbot
            - Answers from SQL data & documents
            - Intent-based routing (data / knowledge)
            - Natural language to SQL
            - Model-agnostic (Gemini / GPT / Nvidia)
            - Conversational memory
            """
        )

    st.markdown("---")

    # ── Database Status ──
    st.markdown("### 🗄️ Database Status")

    try:
        from scrapers.price_scraper import (
            get_db_dates,
            get_last_update_check,
            get_record_count,
        )
        from modules.doc_processor import get_total_chunks, get_indexed_documents

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Price Records", f"{get_record_count():,}")
        with col2:
            _, latest_date = get_db_dates()
            st.metric("Latest Auction Date", latest_date or "N/A")
        with col3:
            st.metric("Last Update Check", get_last_update_check() or "Never")
        with col4:
            st.metric("DB File Modified", _db_file_modified())

        st.markdown("")

        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric("Vector DB Chunks", f"{get_total_chunks():,}")
        with col6:
            docs = get_indexed_documents()
            st.metric("Indexed Documents", f"{len(docs)}")
        with col7:
            st.metric("Update Frequency", "Daily (automated)")
        with col8:
            st.metric("Data Source", "Indian Spices Board")

    except Exception as exc:
        st.warning(f"Could not load status: {exc}")

    st.markdown("---")

    # ── Technology Stack ──
    st.markdown("### 🛠️ Technology Stack")

    tech_data = {
        "Component": [
            "Dashboard",
            "Charts",
            "Database",
            "Web Scraping",
            "LLM Gateway",
            "Document Parsing",
            "Embeddings",
            "Vector Database",
            "Automation",
            "Hosting",
        ],
        "Technology": [
            "Streamlit",
            "Plotly",
            "SQLite",
            "BeautifulSoup + Requests",
            "LiteLLM (model-agnostic)",
            "Docling (IBM)",
            "Google Gemini Embedding",
            "ChromaDB (file-based)",
            "GitHub Actions",
            "Streamlit Cloud",
        ],
        "Purpose": [
            "Interactive web app framework",
            "Interactive data visualization",
            "Structured data storage (prices, rainfall, production)",
            "Daily auction data collection",
            "Switch between Gemini / GPT / Nvidia NIM",
            "PDF, DOCX, XLSX, images → structured chunks",
            "Multimodal text & image embeddings",
            "Semantic search over documents",
            "Daily cron jobs for data updates",
            "Cloud deployment (free tier)",
        ],
    }
    st.table(tech_data)

    st.markdown("---")

    # ── LLM Configuration ──
    st.markdown("### 🔧 Current LLM Configuration")

    try:
        from modules.llm_provider import get_provider_info

        info = get_provider_info()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"**LLM Model:** `{info['llm_model']}`")
        with col2:
            st.markdown(f"**Embedding:** `{info['embedding_model']}`")
        with col3:
            st.markdown(f"**Provider:** `{info['provider']}`")

        st.markdown(
            """
            > **Switching models:** Update the `LLM_MODEL` value in Streamlit Secrets.
            >
            > Examples:
            > - `gemini/gemini-2.0-flash` (Google)
            > - `nvidia_nim/minimaxai/minimax-m3` (Nvidia NIM)
            > - `gpt-4o` (OpenAI)
            """
        )
    except Exception:
        st.caption("LLM configuration not available.")

    st.markdown("---")

    # ── Data Sources ──
    st.markdown("### 📡 Data Sources")
    st.markdown(
        """
        | Data | Source | Update |
        |------|--------|--------|
        | Auction Prices | [Indian Spices Board](https://www.indianspices.com/marketing/price/domestic/daily-price-small.html) | Daily (auto) |
        | Rainfall | Manual / IMD | Periodic |
        | Production | Manual / Spices Board Reports | Periodic |
        | Documents | User uploads & URLs | On-demand |
        """
    )

    st.markdown("---")

    # ── Footer ──
    st.markdown(
        """
        <div style='text-align: center; color: #888; padding: 20px;'>
            <p><strong>Cardamom Business Intelligence v2.0</strong></p>
            <p>Built by <a href="https://github.com/ansSanthoshM" target="_blank">Santhosh M</a>
               · <a href="https://sites.google.com/view/santh2products" target="_blank">Santh2 Products</a></p>
            <p><small>Open Source · Powered by AI · Data-Driven Decisions</small></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
