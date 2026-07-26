"""
Web Scraper for Indian Spices Board — Cardamom Daily Auction Prices.

Source : https://www.indianspices.com/marketing/price/domestic/daily-price-small.html
Storage: SQLite  →  data/cardamom_data.db  (table: cardamom_prices)

Features
--------
* Scrapes ALL pages of the paginated table.
* Multiple rows per date are preserved (one per auctioneer).
* Incremental update: compares latest date in DB and scrapes only newer data.
* Designed to run both inside the Streamlit app ("Update Now" button)
  and from GitHub Actions (daily cron job).
"""

import os
import time
import sqlite3
from datetime import datetime
from typing import Optional, List

import requests
import pandas as pd
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Paths ──
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "cardamom_data.db")

# How many pages to scrape. 'all' = every page; integer = cap.
PAGES_TO_SCRAPE = "all"

# Polite delay between HTTP requests (seconds)
REQUEST_DELAY = 2

# ── Logging ──

def _log(message: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] [%s] %s" % (ts, level, message)
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode('ascii', 'replace').decode('ascii'), flush=True)


# ── Database helpers ──

def _ensure_db() -> None:
    """Create the database and tables if they don't exist yet."""
    from scripts.init_db import initialize_database
    initialize_database(DB_PATH)


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def has_existing_data(db_path: Optional[str] = None) -> bool:
    """Return True when the database file exists and contains at least one row."""
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cardamom_prices")
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def get_last_scraped_date() -> Optional[str]:
    """Return the most recent auction date in the DB (YYYY-MM-DD) or None."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(date_of_auction) FROM cardamom_prices")
        result = cur.fetchone()[0]
        conn.close()
        return result
    except Exception:
        return None


def get_last_update_check() -> Optional[str]:
    """Return the date of the last scrape-check run (YYYY-MM-DD) or None."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS scrape_metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        cur.execute("SELECT value FROM scrape_metadata WHERE key = 'last_update_date'")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _set_last_update_check(date_str: str) -> None:
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS scrape_metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        cur.execute(
            "INSERT OR REPLACE INTO scrape_metadata (key, value) VALUES ('last_update_date', ?)",
            (date_str,),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        _log(f"Error saving last-update-date: {exc}", "ERROR")


def get_record_count() -> int:
    """Total rows in cardamom_prices."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cardamom_prices")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# ── Scraping ──

_BASE_URL = "https://www.indianspices.com/marketing/price/domestic/daily-price-small.html"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}

_EXPECTED_COLUMNS = [
    "Date of Auction",
    "Auctioneer",
    "No.of Lots",
    "Total Qty Arrived (Kgs)",
    "Qty Sold (Kgs)",
    "MaxPrice (Rs./Kg)",
    "Avg.Price (Rs./Kg)",
]


def scrape_page(page_num: int = 1) -> Optional[pd.DataFrame]:
    """Scrape a single page of the auction table.

    Returns a raw DataFrame or None when no data is found / on error.
    """
    url = f"{_BASE_URL}?page={page_num}"
    try:
        _log(f"Scraping page {page_num} …")
        resp = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
        resp.raise_for_status()
    except requests.RequestException as exc:
        _log(f"HTTP error on page {page_num}: {exc}", "ERROR")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # The page may contain several <table> elements; find the auction one.
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header = None
        data_rows: List[List[str]] = []

        for tr in rows:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            # Detect the header row
            if "Date of Auction" in cells and "Auctioneer" in cells:
                header = cells
                continue
            if header and len(cells) >= len(header):
                data_rows.append(cells[: len(header)])

        if header and data_rows:
            df = pd.DataFrame(data_rows, columns=header)
            if "Date of Auction" in df.columns and "Auctioneer" in df.columns:
                # Drop 'Sno' if present
                if "Sno" in df.columns:
                    df = df.drop(columns=["Sno"])
                # Remove accidental repeated header rows
                df = df[df["Date of Auction"] != "Date of Auction"]
                # Keep only expected columns that actually exist
                keep = [c for c in _EXPECTED_COLUMNS if c in df.columns]
                df = df[keep] if keep else df
                if len(df) > 0:
                    _log("  -> %d records from page %d" % (len(df), page_num))
                    return df

    _log(f"No auction table found on page {page_num}", "WARN")
    return None


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names and data types."""
    rename_map = {
        "Date of Auction": "date_of_auction",
        "Auctioneer": "auctioneer",
        "No.of Lots": "no_of_lots",
        "Total Qty Arrived (Kgs)": "total_qty_arrived",
        "Qty Sold (Kgs)": "qty_sold",
        "MaxPrice (Rs./Kg)": "max_price",
        "Avg.Price (Rs./Kg)": "avg_price",
    }
    df = df.rename(columns=rename_map)

    for col in ("no_of_lots", "total_qty_arrived", "qty_sold", "max_price", "avg_price"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "date_of_auction" in df.columns:
        df["date_of_auction"] = (
            pd.to_datetime(df["date_of_auction"], format="mixed", dayfirst=True)
            .dt.strftime("%Y-%m-%d")
        )

    df = df.drop_duplicates(subset=["date_of_auction", "auctioneer"])
    return df


def _save(df: pd.DataFrame) -> int:
    """Insert cleaned rows into the DB. Returns count of *new* rows inserted."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM cardamom_prices")
    before = cur.fetchone()[0]

    try:
        for _, row in df.iterrows():
            cur.execute(
                """INSERT OR IGNORE INTO cardamom_prices
                   (date_of_auction, auctioneer, no_of_lots,
                    total_qty_arrived, qty_sold, max_price, avg_price)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.get("date_of_auction"),
                    row.get("auctioneer"),
                    row.get("no_of_lots"),
                    row.get("total_qty_arrived"),
                    row.get("qty_sold"),
                    row.get("max_price"),
                    row.get("avg_price"),
                ),
            )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM cardamom_prices")
        after = cur.fetchone()[0]
        inserted = after - before
        _log("  -> %d new rows inserted (total %d)" % (inserted, after))
        return inserted
    except Exception as exc:
        _log(f"DB insert error: {exc}", "ERROR")
        conn.rollback()
        return 0
    finally:
        conn.close()


def scrape_all_pages(
    max_pages: Optional[int] = None,
    stop_at_date: Optional[str] = None,
) -> int:
    """Iterate through all paginated pages, clean, and save to DB.

    Args:
        max_pages: Hard cap on the number of pages to fetch (None = unlimited).
        stop_at_date: Stop once a page contains a date ≤ this value (YYYY-MM-DD).

    Returns:
        Total number of *new* rows inserted across all pages.
    """
    page = 1
    total_inserted = 0

    while True:
        if max_pages and page > max_pages:
            break

        raw_df = scrape_page(page)
        if raw_df is None or raw_df.empty:
            _log(f"End of data reached at page {page}")
            break

        cleaned = _clean(raw_df.copy())
        if cleaned.empty:
            _log(f"Page {page} produced no valid rows after cleaning")
            page += 1
            time.sleep(REQUEST_DELAY)
            continue

        inserted = _save(cleaned)
        total_inserted += inserted

        # Check if we've reached already-known dates
        if stop_at_date:
            try:
                dates = cleaned["date_of_auction"].tolist()
                if any(d <= stop_at_date for d in dates):
                    _log(
                        f"Reached date ≤ {stop_at_date} on page {page}. "
                        "Stopping incremental scrape."
                    )
                    break
            except Exception as exc:
                _log(f"Error checking stop date: {exc}", "WARN")

        time.sleep(REQUEST_DELAY)
        page += 1

    return total_inserted


# ── Public entry points ──

def run_full_scrape() -> bool:
    """Initial / full scrape — fetches all available history.

    Returns True on success (at least 1 row inserted).
    """
    _log("=" * 70)
    _log("FULL SCRAPE — fetching all historical data")
    _log("=" * 70)

    _ensure_db()

    max_pg = (
        None
        if str(PAGES_TO_SCRAPE).lower() == "all"
        else int(PAGES_TO_SCRAPE)
    )
    inserted = scrape_all_pages(max_pages=max_pg)

    _set_last_update_check(datetime.now().strftime("%Y-%m-%d"))
    _log(f"Full scrape complete — {inserted} new rows")
    return inserted > 0


def run_incremental_scrape() -> bool:
    """Delta scrape — only fetches pages with dates newer than what's in the DB.

    Returns True when the run completes (even if 0 new rows).
    """
    _log("=" * 70)
    _log("INCREMENTAL SCRAPE — fetching new data only")
    _log("=" * 70)

    _ensure_db()

    last_date = get_last_scraped_date()
    _log(f"Last date in DB: {last_date}")

    max_pg = (
        None
        if str(PAGES_TO_SCRAPE).lower() == "all"
        else int(PAGES_TO_SCRAPE)
    )
    inserted = scrape_all_pages(max_pages=max_pg, stop_at_date=last_date)

    _set_last_update_check(datetime.now().strftime("%Y-%m-%d"))
    _log(f"Incremental scrape complete — {inserted} new rows")
    return True


def auto_scrape() -> bool:
    """Smart entry point: full scrape if DB is empty, else incremental."""
    _ensure_db()
    if not has_existing_data():
        return run_full_scrape()

    today = datetime.now().strftime("%Y-%m-%d")
    last_check = get_last_update_check()
    if last_check == today:
        _log("Already checked today — skipping.")
        return True

    return run_incremental_scrape()


# ── CLI ──
if __name__ == "__main__":
    auto_scrape()
