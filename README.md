# 🌿 Cardamom Business Intelligence

An AI-powered data platform for Indian Cardamom market analysis — combining **real-time auction data**, **document intelligence**, and a **RAG chatbot** in a single Streamlit application.

**Live Dashboard:** [Streamlit Cloud](https://cardamom-business.streamlit.app) *(Coming Soon)*

---

## ✨ Features

### 📊 Dashboard
- Interactive dual-axis charts (price + quantity) with Plotly
- KPI cards: latest prices, total quantity, data span
- Date range presets (3m, 6m, 1y, All) or custom
- Auctioneer-level filtering
- Data table with CSV export
- **"Update Now" button** — scrape latest data on-demand

### 📚 Knowledge Base & RAG Chatbot
- **Upload files**: PDF, DOCX, XLSX, images, and more
- **Scrape web URLs**: Download and index online content
- **Multimodal parsing**: Docling extracts text, tables, charts, images
- **Vector search**: ChromaDB with Gemini embeddings
- **Hybrid RAG**: Queries both SQL database AND document knowledge
- **AI chatbot** with source citations and SQL query display

### 🤖 Model-Agnostic AI
- Powered by **LiteLLM** — switch LLM providers by changing one config line
- Default: **Google Gemini 2.0 Flash** (free tier)
- Alternatives: **Nvidia NIM (MiniMax M3)**, **OpenAI GPT-4o**, and 100+ more
- Multimodal embeddings via Google Gemini Embedding API

---

## 🏗️ Project Structure

```
CardamomBusiness_1/
├── app.py                          # Main Streamlit app (3 tabs)
├── modules/
│   ├── dashboard.py                # Tab 1: Charts + KPIs
│   ├── knowledge_base.py           # Tab 2: Upload + Chat
│   ├── about.py                    # Tab 3: Info + Status
│   ├── llm_provider.py             # LiteLLM wrapper + Embeddings
│   ├── rag_engine.py               # Hybrid RAG (Vector + SQL)
│   ├── sql_agent.py                # Natural language → SQL
│   └── doc_processor.py            # Docling parser + ChromaDB
├── scrapers/
│   └── price_scraper.py            # Indian Spices Board scraper
├── scripts/
│   ├── init_db.py                  # Database schema setup
│   ├── daily_update.py             # GitHub Actions orchestrator
│   └── ingest_source.py            # Document ingestion CLI
├── data/
│   ├── cardamom_data.db            # SQLite database (auto-generated)
│   └── chroma_db/                  # ChromaDB vector store
├── uploaded_docs/                   # Raw uploaded files
├── .github/workflows/
│   ├── daily_update.yml            # Daily cron (9 PM IST)
│   └── ingest_document.yml         # On-demand document ingestion
├── .streamlit/
│   └── config.toml                 # Theme & server config
├── requirements.txt
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- A Google Gemini API key ([get one free](https://aistudio.google.com/apikey))

### 1. Clone & Setup

```bash
git clone https://github.com/ansSanthoshM/CardamomBusiness_1.git
cd CardamomBusiness_1
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API Keys

Create `.streamlit/secrets.toml` (never commit this!):

```toml
GEMINI_API_KEY = "your-gemini-api-key-here"
LLM_MODEL = "gemini/gemini-2.0-flash"
EMBEDDING_MODEL = "models/text-embedding-004"
```

### 3. Initialize & Run

```bash
# Initialize database
python scripts/init_db.py

# Run the app (data will auto-scrape on first launch)
streamlit run app.py
```

The app opens at `http://localhost:8501`. On first run, it fetches all historical price data (may take 5–10 minutes).

---

## 🔄 Switching LLM Providers

Change a single value in `.streamlit/secrets.toml`:

```toml
# Google Gemini (default, free tier)
LLM_MODEL = "gemini/gemini-2.0-flash"
GEMINI_API_KEY = "your-key"

# Nvidia NIM — MiniMax M3
LLM_MODEL = "nvidia_nim/minimaxai/minimax-m3"
NVIDIA_NIM_API_KEY = "your-key"

# OpenAI
LLM_MODEL = "gpt-4o"
OPENAI_API_KEY = "your-key"
```

No code changes required — LiteLLM handles the translation.

---

## 🌐 Deploy to Streamlit Cloud

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Initial commit: Cardamom Business Intelligence v2"
git push origin main
```

### Step 2: Deploy

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub → "New app"
3. Select: `ansSanthoshM/CardamomBusiness_1`, branch `main`, file `app.py`
4. Add secrets in the **Secrets** section (same as `secrets.toml`)
5. Click **Deploy**

### Step 3: Set Up GitHub Actions

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Add secret: `GEMINI_API_KEY` = your API key
3. Enable Actions in repo settings
4. The daily update will run automatically at 9:00 PM IST

---

## 📅 Daily Automation

The GitHub Actions workflow (`.github/workflows/daily_update.yml`) runs every day:

1. **Scrapes** new auction data from Indian Spices Board
2. **Updates** the SQLite database with new rows only
3. **Commits** the updated `.db` file back to the repo
4. **Streamlit Cloud** automatically picks up the change

**Schedule:** 15:30 UTC (9:00 PM IST) daily

---

## 📝 Database Schema

### cardamom_prices
| Column | Type | Description |
|--------|------|-------------|
| date_of_auction | TEXT | Auction date (YYYY-MM-DD) |
| auctioneer | TEXT | Auction centre name |
| total_qty_arrived | REAL | Quantity in Kgs |
| max_price | REAL | Maximum price (₹/Kg) |
| avg_price | REAL | Average price (₹/Kg) |

### rainfall_data
| Column | Type | Description |
|--------|------|-------------|
| year | INTEGER | Year |
| region | TEXT | Region (default: Kerala) |
| rainfall_mm | REAL | Annual rainfall in mm |

### production_data
| Column | Type | Description |
|--------|------|-------------|
| year | INTEGER | Year |
| month | INTEGER | Month (1-12) |
| production_qty_tonnes | REAL | Production in tonnes |

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|-----------|
| **Web App** | Streamlit |
| **Charts** | Plotly |
| **Database** | SQLite |
| **Web Scraping** | BeautifulSoup + Requests |
| **LLM Gateway** | LiteLLM (model-agnostic) |
| **Doc Parsing** | Docling (IBM) |
| **Embeddings** | Google Gemini Embedding API |
| **Vector DB** | ChromaDB (file-based) |
| **Automation** | GitHub Actions |
| **Hosting** | Streamlit Cloud |

---

## 👤 Author

**Santhosh M**
- GitHub: [@ansSanthoshM](https://github.com/ansSanthoshM)
- Website: [Santh2 Products](https://sites.google.com/view/santh2products)

---

## 📄 License

Open source — for personal and educational use.

---

**Last Updated:** 2026-07-25
**Status:** Active Development ✓
