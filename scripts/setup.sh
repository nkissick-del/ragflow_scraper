#!/bin/bash
#
# Setup script for PDF Scraper
# Run this script to initialize the project for local development or Docker deployment
#

set -e

echo "=========================================="
echo "PDF Scraper Setup Script"
echo "=========================================="
echo

# Detect if running in Docker or locally
if [ -f /.dockerenv ]; then
    echo "Running inside Docker container"
    IN_DOCKER=true
else
    echo "Running on host machine"
    IN_DOCKER=false
fi

# Create required directories
echo "Creating directories..."
mkdir -p data/scraped data/metadata data/state data/logs
mkdir -p config/scrapers
echo "  ✓ Directories created"

# Create .gitkeep files
touch data/scraped/.gitkeep
touch data/metadata/.gitkeep
touch data/state/.gitkeep
touch data/logs/.gitkeep
touch config/scrapers/.gitkeep
echo "  ✓ .gitkeep files created"

# Copy .env.example to .env if it doesn't exist
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "  ✓ Created .env from .env.example"
        echo "    → Edit .env to configure your settings"
    fi
else
    echo "  ✓ .env already exists"
fi

# For local development
if [ "$IN_DOCKER" = false ]; then
    # Check Python version
    echo
    echo "Checking Python version..."
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        echo "  ✓ Python $PYTHON_VERSION found"
    else
        echo "  ✗ Python 3 not found. Please install Python 3.11+"
        exit 1
    fi

    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        echo
        echo "Creating virtual environment..."
        python3 -m venv .venv
        echo "  ✓ Virtual environment created"
    else
        echo "  ✓ Virtual environment already exists"
    fi

    # Activate and install dependencies
    echo
    echo "Installing dependencies..."
    source .venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    echo "  ✓ Dependencies installed"

    echo
    echo "=========================================="
    echo "Local Setup Complete!"
    echo "=========================================="
    echo
    echo "To start the application:"
    echo "  1. Activate virtual environment:"
    echo "     source .venv/bin/activate"
    echo
    echo "  2. Start with Docker Compose (includes FlareSolverr):"
    echo "     make dev-up"
    echo
    echo "  OR run a scraper directly:"
    echo "     python scripts/run_scraper.py --scraper aemo"
    echo
else
    echo
    echo "=========================================="
    echo "Docker Setup Complete!"
    echo "=========================================="
fi

echo
echo "Access the web UI at: http://localhost:5000"
echo
