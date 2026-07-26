"""
Database Initialization Script
Creates SQLite database with all required tables for Cardamom Business.

Tables:
  - cardamom_prices  : Daily auction prices (date, auctioneer, qty, price)
  - rainfall_data    : Yearly rainfall values by region
  - production_data  : Monthly production quantities
  - scrape_metadata  : Key-value store for tracking update timestamps
"""

import sqlite3
import os
from typing import Optional

# Database lives under data/ relative to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "cardamom_data.db")


def get_db_path() -> str:
    """Return the canonical database path, creating the parent dir if needed."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open (or create) an SQLite connection to the project database."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all application tables if they do not already exist."""
    cursor = conn.cursor()

    # ── Migration: drop old schema if the UNIQUE constraint changed ──
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='cardamom_prices';"
    )
    row = cursor.fetchone()
    if row:
        ddl = row[0]
        if (
            "date_of_auction TEXT UNIQUE" in ddl
            or "UNIQUE(date_of_auction, auctioneer)" not in ddl
        ):
            cursor.execute("DROP TABLE IF EXISTS cardamom_prices")
            cursor.execute("DROP TABLE IF EXISTS scrape_metadata")

    # ── Table 1: Daily auction prices ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cardamom_prices (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            date_of_auction     TEXT    NOT NULL,
            auctioneer          TEXT,
            no_of_lots          REAL,
            total_qty_arrived   REAL,
            qty_sold            REAL,
            max_price           REAL,
            avg_price           REAL,
            scraped_date        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date_of_auction, auctioneer)
        );
    """)

    # ── Table 2: Yearly rainfall ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rainfall_data (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            year          INTEGER NOT NULL,
            region        TEXT    DEFAULT 'Kerala',
            rainfall_mm   REAL   NOT NULL,
            data_source   TEXT,
            UNIQUE(year, region)
        );
    """)

    # ── Table 3: Monthly production ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS production_data (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            year                   INTEGER NOT NULL,
            month                  INTEGER NOT NULL,
            production_qty_tonnes  REAL    NOT NULL,
            region                 TEXT    DEFAULT 'India',
            data_source            TEXT,
            UNIQUE(year, month, region)
        );
    """)

    # ── Metadata key-value store ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_metadata (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    conn.commit()


def initialize_database(db_path: Optional[str] = None) -> str:
    """Full initialization: create dir, database, and all tables.

    Returns the path to the created database.
    """
    path = db_path or get_db_path()
    conn = get_connection(path)
    create_tables(conn)
    conn.close()
    print(f"[init_db] Database initialized at {path}")
    return path


# ─── CLI entry point ───
if __name__ == "__main__":
    initialize_database()
