"""
Daily Update Script — Orchestrator for GitHub Actions daily cron job.
=====================================================================

Runs from the repo root by GitHub Actions. Steps:
  1. Initialize the database (create tables if needed).
  2. Run incremental price scrape (fetch only new dates).
  3. (Future) Update rainfall and production data.

Usage:
  python scripts/daily_update.py
"""

import sys
import os

# Ensure project root is on the import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> bool:
    """Run the full daily update pipeline."""
    from scripts.init_db import initialize_database
    from scrapers.price_scraper import auto_scrape

    print("=" * 60)
    print("  DAILY UPDATE — Cardamom Business Intelligence")
    print("=" * 60)

    # Step 1: Ensure database schema is up to date
    print("\n[1/2] Initializing database …")
    initialize_database()

    # Step 2: Scrape prices (incremental)
    print("\n[2/2] Running price scraper …")
    ok = auto_scrape()

    if ok:
        print("\n✅ Daily update completed successfully.")
    else:
        print("\n⚠️ Daily update completed with warnings.")

    return ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
