"""
SQL Agent — Natural-language to SQL for the Cardamom database.
==============================================================

Converts user questions about prices, rainfall, and production into
safe, read-only SQL queries against the SQLite database, executes them,
and returns structured results ready for the LLM to summarise.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Optional, List, Dict, Tuple

import pandas as pd

# ── Paths ──
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "cardamom_data.db")

# ── Schema description fed to the LLM ──
SCHEMA_DESCRIPTION = """
You have access to a SQLite database with the following tables:

TABLE: cardamom_prices
  - id                  INTEGER PRIMARY KEY
  - date_of_auction     TEXT (YYYY-MM-DD)
  - auctioneer          TEXT (name of auction centre)
  - no_of_lots          REAL
  - total_qty_arrived   REAL (kilograms)
  - qty_sold            REAL (kilograms)
  - max_price           REAL (Rs. per Kg)
  - avg_price           REAL (Rs. per Kg)
  - scraped_date        TIMESTAMP

TABLE: rainfall_data
  - id            INTEGER PRIMARY KEY
  - year          INTEGER
  - region        TEXT (default 'Kerala')
  - rainfall_mm   REAL
  - data_source   TEXT

TABLE: production_data
  - id                     INTEGER PRIMARY KEY
  - year                   INTEGER
  - month                  INTEGER (1-12)
  - production_qty_tonnes  REAL
  - region                 TEXT (default 'India')
  - data_source            TEXT

IMPORTANT RULES:
- Only generate SELECT statements. Never INSERT, UPDATE, DELETE, DROP, or ALTER.
- Use strftime() for date operations on date_of_auction.
- Limit results to 50 rows unless the user asks for more.
- When computing averages across auctioneers on the same date, GROUP BY date_of_auction.
- Return ONLY the SQL query, no explanation. Wrap it in ```sql ... ``` markers.
"""


def _get_conn() -> sqlite3.Connection:
    """Open a read-only connection to the database."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    # Open in read-only mode via URI
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    return conn


def get_schema_summary() -> str:
    """Return the schema description string for the LLM prompt."""
    return SCHEMA_DESCRIPTION


def generate_sql(user_question: str) -> str:
    """Ask the LLM to produce a SQL query for the user's question.

    Returns the raw SQL string.
    """
    from modules.llm_provider import chat

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert SQL analyst. Given the database schema below "
                "and a user question, produce a single SQLite-compatible SELECT query.\n"
                + SCHEMA_DESCRIPTION
            ),
        },
        {
            "role": "user",
            "content": user_question,
        },
    ]

    resp = chat(messages, temperature=0.0, max_tokens=1024)
    raw = resp.choices[0].message.content

    # Extract SQL from markdown fences if present
    sql = _extract_sql(raw)
    return sql


def _extract_sql(text: str) -> str:
    """Pull the SQL statement out of LLM markdown formatting."""
    import re

    # Try ```sql ... ``` block
    match = re.search(r"```sql\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Try ``` ... ``` block
    match = re.search(r"```\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Assume the whole text is SQL
    return text.strip()


def validate_sql(sql: str) -> Tuple[bool, str]:
    """Basic safety check — only allow SELECT statements."""
    normalised = sql.strip().upper()

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE", "ATTACH"]
    for kw in forbidden:
        # Check for keyword as a word boundary
        if kw in normalised.split():
            return False, f"Forbidden keyword detected: {kw}"

    if not normalised.startswith("SELECT"):
        return False, "Query must start with SELECT"

    return True, "OK"


def execute_sql(sql: str) -> Dict[str, Any]:
    """Execute a validated SQL query and return results.

    Returns dict with:
      - success: bool
      - sql: str
      - columns: list[str]
      - rows: list[tuple]
      - dataframe: pd.DataFrame | None
      - error: str | None
    """
    is_safe, reason = validate_sql(sql)
    if not is_safe:
        return {
            "success": False,
            "sql": sql,
            "columns": [],
            "rows": [],
            "dataframe": None,
            "error": f"Blocked: {reason}",
        }

    try:
        conn = _get_conn()
        df = pd.read_sql_query(sql, conn)
        conn.close()

        return {
            "success": True,
            "sql": sql,
            "columns": list(df.columns),
            "rows": [tuple(row) for row in df.values],
            "dataframe": df,
            "error": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "sql": sql,
            "columns": [],
            "rows": [],
            "dataframe": None,
            "error": str(exc),
        }


def ask_sql(user_question: str) -> Dict[str, Any]:
    """End-to-end: question → SQL → execute → results.

    Returns dict with sql, results, and a text summary.
    """
    try:
        sql = generate_sql(user_question)
        result = execute_sql(sql)

        if not result["success"]:
            return {
                "sql": sql,
                "result": result,
                "context_text": f"SQL query failed: {result['error']}",
            }

        # Build a text representation for the LLM context
        df = result["dataframe"]
        if df is not None and not df.empty:
            # Truncate for context window
            display_df = df.head(30)
            table_text = display_df.to_markdown(index=False)
            context = (
                f"SQL Query: {sql}\n\n"
                f"Results ({len(df)} rows, showing first {len(display_df)}):\n\n"
                f"{table_text}"
            )
        else:
            context = f"SQL Query: {sql}\n\nNo results returned."

        return {
            "sql": sql,
            "result": result,
            "context_text": context,
        }

    except Exception as exc:
        return {
            "sql": "",
            "result": {"success": False, "error": str(exc)},
            "context_text": f"Error processing SQL query: {exc}",
        }


def get_quick_stats() -> Dict[str, Any]:
    """Fetch key aggregate stats from the DB for the dashboard."""
    stats = {}
    try:
        conn = _get_conn()

        # Total records
        stats["total_records"] = pd.read_sql_query(
            "SELECT COUNT(*) as cnt FROM cardamom_prices", conn
        ).iloc[0]["cnt"]

        # Date range
        date_range = pd.read_sql_query(
            "SELECT MIN(date_of_auction) as min_date, MAX(date_of_auction) as max_date FROM cardamom_prices",
            conn,
        ).iloc[0]
        stats["min_date"] = date_range["min_date"]
        stats["max_date"] = date_range["max_date"]

        # Latest price stats (most recent date, aggregated across auctioneers)
        latest = pd.read_sql_query(
            """SELECT date_of_auction,
                      ROUND(AVG(avg_price), 2) as avg_price,
                      ROUND(MAX(max_price), 2) as max_price,
                      ROUND(SUM(total_qty_arrived), 0) as total_qty
               FROM cardamom_prices
               WHERE date_of_auction = (SELECT MAX(date_of_auction) FROM cardamom_prices)
               GROUP BY date_of_auction""",
            conn,
        )
        if not latest.empty:
            stats["latest_date"] = latest.iloc[0]["date_of_auction"]
            stats["latest_avg_price"] = latest.iloc[0]["avg_price"]
            stats["latest_max_price"] = latest.iloc[0]["max_price"]
            stats["latest_total_qty"] = latest.iloc[0]["total_qty"]

        # All-time stats
        alltime = pd.read_sql_query(
            """SELECT ROUND(AVG(avg_price), 2) as overall_avg,
                      ROUND(MIN(avg_price), 2) as overall_min,
                      ROUND(MAX(max_price), 2) as overall_max,
                      ROUND(SUM(total_qty_arrived), 0) as total_qty
               FROM cardamom_prices""",
            conn,
        ).iloc[0]
        stats["overall_avg_price"] = alltime["overall_avg"]
        stats["overall_min_price"] = alltime["overall_min"]
        stats["overall_max_price"] = alltime["overall_max"]
        stats["overall_total_qty"] = alltime["total_qty"]

        conn.close()
    except Exception as exc:
        stats["error"] = str(exc)

    return stats
