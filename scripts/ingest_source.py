"""
Document Ingestion Script — Process a file or URL into the vector DB.
=====================================================================

Designed to be called from GitHub Actions (workflow_dispatch) or CLI.

Usage:
  # Process a local file
  python scripts/ingest_source.py --file path/to/document.pdf

  # Process a URL
  python scripts/ingest_source.py --url https://example.com/report.pdf
"""

import sys
import os
import argparse

# Ensure project root is on the import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> bool:
    parser = argparse.ArgumentParser(description="Ingest a document into the vector DB.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to a local file to ingest.")
    group.add_argument("--url", help="URL to download and ingest.")
    args = parser.parse_args()

    # Ensure DB is initialized
    from scripts.init_db import initialize_database
    initialize_database()

    if args.file:
        if not os.path.exists(args.file):
            print(f"❌ File not found: {args.file}")
            return False

        print(f"📄 Processing file: {args.file}")
        from modules.doc_processor import process_file
        result = process_file(args.file)

    else:
        print(f"🌐 Processing URL: {args.url}")
        from modules.doc_processor import process_url
        result = process_url(args.url)

    # Report result
    print(f"\nResult:")
    print(f"  Source:  {result['source']}")
    print(f"  Chunks: {result['chunks_created']}")
    print(f"  Status: {result['status']}")

    return result["status"] == "success"


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
