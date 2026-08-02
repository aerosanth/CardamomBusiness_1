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

import sys
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)

from modules.logger import get_app_logger
scraper_logger = get_app_logger("price_scraper")

def _log(message: str, level: str = "INFO") -> None:
    level = level.upper()
    if level == "WARN":
        scraper_logger.warning(message)
    elif level == "ERROR":
        scraper_logger.error(message)
    else:
        scraper_logger.info(message)


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


def get_db_dates() -> tuple[Optional[str], Optional[str]]:
    """Return the (oldest_date, latest_date) in the DB (YYYY-MM-DD) or (None, None)."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT MIN(date_of_auction), MAX(date_of_auction) FROM cardamom_prices")
        row = cur.fetchone()
        conn.close()
        return (row[0], row[1]) if row else (None, None)
    except Exception:
        return None, None


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
    max_retries = 3
    for attempt in range(max_retries):
        try:
            _log(f"Scraping page {page_num} (Attempt {attempt + 1}/{max_retries}) …")
            resp = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
            resp.raise_for_status()
            break # Success, exit retry loop
        except requests.RequestException as exc:
            _log(f"HTTP error on page {page_num} (Attempt {attempt + 1}): {exc}", "WARN")
            if attempt == max_retries - 1:
                _log(f"Failed to scrape page {page_num} after {max_retries} attempts.", "ERROR")
                return None
            time.sleep(REQUEST_DELAY * 2) # Wait longer before retrying

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

import re

def get_last_page_number(soup: BeautifulSoup) -> int:
    links = soup.find_all('a', href=True)
    max_page = 1
    for a in links:
        m = re.search(r'page=(\d+)', a['href'])
        if m:
            page = int(m.group(1))
            if page > max_page:
                max_page = page
    return max_page

def find_page_for_date(target_date: str, last_page: int) -> int:
    """Uses binary search to find the page number containing the target date."""
    if not target_date:
        return 1
    low = 1
    high = last_page
    
    while low <= high:
        mid = (low + high) // 2
        df = scrape_page(mid)
        if df is None or df.empty:
            high = mid - 1
            continue
            
        cleaned = _clean(df.copy())
        if cleaned.empty:
            high = mid - 1
            continue
            
        page_dates = cleaned['date_of_auction'].dropna().tolist()
        if not page_dates:
            high = mid - 1
            continue
            
        page_max_date = max(page_dates)
        page_min_date = min(page_dates)
        
        if target_date > page_max_date:
            high = mid - 1
        elif target_date < page_min_date:
            low = mid + 1
        else:
            return mid
            
    return min(max(1, low), last_page)


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

    _, last_date = get_db_dates()
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
    """Smart entry point: full scrape if DB is empty, else smart update."""
    _ensure_db()
    
    db_oldest_date, db_latest_date = get_db_dates()
    _log(f"DB Oldest Date: {db_oldest_date}, DB Latest Date: {db_latest_date}")
    
    _log("Fetching page 1 to find latest web date and last page number...")
    url = f"{_BASE_URL}?page=1"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            last_page = get_last_page_number(soup)
            break
        except Exception as exc:
            _log(f"Failed to fetch page 1 metadata (Attempt {attempt + 1}): {exc}", "WARN")
            if attempt == max_retries - 1:
                _log("Failed to fetch page 1 metadata after all attempts.", "ERROR")
                return False
            time.sleep(REQUEST_DELAY * 2)
        
    df_1 = scrape_page(1)
    if df_1 is not None and not df_1.empty:
        cleaned_1 = _clean(df_1.copy())
        web_latest_date = cleaned_1['date_of_auction'].max() if not cleaned_1.empty else None
    else:
        web_latest_date = None
        
    _log(f"Fetching last page ({last_page}) to find oldest web date...")
    df_last = scrape_page(last_page)
    if df_last is not None and not df_last.empty:
        cleaned_last = _clean(df_last.copy())
        web_oldest_date = cleaned_last['date_of_auction'].min() if not cleaned_last.empty else None
    else:
        web_oldest_date = None
        
    _log(f"Web Latest Date: {web_latest_date}, Web Oldest Date: {web_oldest_date}, Last Page: {last_page}")
    
    if not db_oldest_date or not db_latest_date:
        _log("DB is empty. Running full scrape.")
        return run_full_scrape()

    # 1. Backfill (oldest db to last page)
    _log(f"Finding page for DB oldest date: {db_oldest_date}")
    page_for_oldest = find_page_for_date(db_oldest_date, last_page)
    _log(f"DB oldest date found around page {page_for_oldest}. Scraping from {page_for_oldest} to {last_page}")
    
    for p in range(page_for_oldest, last_page + 1):
        df = scrape_page(p)
        if df is not None and not df.empty:
            cleaned = _clean(df.copy())
            if not cleaned.empty:
                _save(cleaned)
        time.sleep(REQUEST_DELAY)
        
    # 2. Forward fill (latest db to page 1)
    _log(f"Finding page for DB latest date: {db_latest_date}")
    page_for_latest = find_page_for_date(db_latest_date, last_page)
    _log(f"DB latest date found around page {page_for_latest}. Scraping from {page_for_latest} down to 1")
    
    for p in range(page_for_latest, 0, -1):
        df = scrape_page(p)
        if df is not None and not df.empty:
            cleaned = _clean(df.copy())
            if not cleaned.empty:
                _save(cleaned)
        time.sleep(REQUEST_DELAY)
        
    _set_last_update_check(datetime.now().strftime("%Y-%m-%d"))
    _log("Smart update complete.")
    return True


# ── CLI ──
if __name__ == "__main__":
    auto_scrape()
