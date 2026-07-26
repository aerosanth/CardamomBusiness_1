"""
🌿 Cardamom Business Intelligence — Main Streamlit Application
================================================================

Multi-tab app:
  Tab 1 — Dashboard   : Price charts, KPIs, data table
  Tab 2 — Knowledge   : Upload docs / URLs + RAG chatbot
  Tab 3 — About       : App info, tech stack, update status
"""

import streamlit as st

# ── Page config (must be first Streamlit call) ──
st.set_page_config(
    page_title="Cardamom Business Intelligence",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──
st.markdown(
    """
    <style>
        /* Subtle top padding */
        .main { padding-top: 1rem; }

        /* Metric cards styling */
        [data-testid="stMetric"] {
            background: linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%);
            border-radius: 0.6rem;
            padding: 0.8rem 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.85rem;
            color: #2E7D32;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.3rem;
            color: #1B5E20;
        }

        /* Tab styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 20px;
            border-radius: 6px 6px 0 0;
        }

        /* Chat messages */
        .stChatMessage {
            border-radius: 0.6rem;
        }

        /* Sidebar header */
        [data-testid="stSidebar"] [data-testid="stMarkdown"] h3 {
            color: #2E7D32;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Header ──
st.title("🌿 Cardamom Business Intelligence")

# ── Tabs ──
tab_dashboard, tab_knowledge, tab_about = st.tabs(
    ["📊 Dashboard", "📚 Knowledge Base", "ℹ️ About"]
)

with tab_dashboard:
    from modules.dashboard import render_dashboard
    render_dashboard()

with tab_knowledge:
    from modules.knowledge_base import render_knowledge_base
    render_knowledge_base()

with tab_about:
    from modules.about import render_about
    render_about()
