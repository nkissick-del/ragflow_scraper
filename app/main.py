#!/usr/bin/env python3
"""
Main entry point for the PDF Scraper Flask application.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import Config
from app.web import create_app
from app.utils import setup_logging


def main():
    """Run the Flask application."""
    # Setup logging
    setup_logging(name="scraper", level=Config.LOG_LEVEL)

    # Create Flask app
    app = create_app()

    # Run the development server
    print(f"\n{'=' * 60}")
    print("PDF Scraper Web Interface")
    print(f"{'=' * 60}")
    print(f"Running on: http://{Config.HOST}:{Config.PORT}")
    print(f"Debug mode: {'enabled' if Config.DEBUG else 'disabled'}")
    print(f"{'=' * 60}\n")

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )


if __name__ == "__main__":
    main()
