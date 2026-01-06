# Multi-Site PDF Scraper with RAGFlow Integration

A modular web scraping system that downloads PDFs and articles from multiple Australian energy sector websites and integrates with RAGFlow for RAG ingestion.

## Features

- **PDF Scrapers**: AEMO, AEMC, AER, ENA, ECA (Australian energy sector documents)
- **Article Scrapers**: RenewEconomy, TheEnergy, Guardian Australia, The Conversation
- Modular scraper architecture - easily add new scrapers
- HTMX-based web interface for configuration and monitoring
- RAGFlow integration with metadata support for document ingestion
- CLI interface for n8n integration
- FlareSolverr support for Cloudflare bypass
- Docker-ready for deployment on Unraid

## Quick Start

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Start Selenium Chrome container
docker run -d -p 4444:4444 --shm-size=2g selenium/standalone-chrome:latest

# Run the web interface
python app/main.py

# Or run a scraper directly
python scripts/run_scraper.py --scraper aemo
```

### Docker Deployment

```bash
docker-compose up --build
```

Access the web UI at http://localhost:5050

## CLI Usage

```bash
# List available scrapers
python scripts/run_scraper.py --list-scrapers

# Run a scraper
python scripts/run_scraper.py --scraper aemo

# Run with options
python scripts/run_scraper.py --scraper aemo --max-pages 5 --output-format json

# Upload to RAGFlow after scraping
python scripts/run_scraper.py --scraper aemo --upload-to-ragflow --dataset-id abc123
```

## Project Structure

```
scraper/
├── app/
│   ├── scrapers/       # Scraper modules
│   ├── services/       # External integrations
│   ├── orchestrator/   # Scheduling and pipelines
│   ├── web/            # Flask web interface
│   └── utils/          # Shared utilities
├── config/             # Configuration files
├── data/               # Downloaded files and state
├── scripts/            # CLI tools
└── docker-compose.yml
```

## Adding a New Scraper

1. Create a new file in `app/scrapers/` (e.g., `my_scraper.py`)
2. Inherit from `BaseScraper` and implement required methods
3. The scraper will be auto-discovered and available via CLI and web UI

```python
from app.scrapers.base_scraper import BaseScraper

class MyScraper(BaseScraper):
    name = "my-scraper"
    description = "Scrapes documents from example.com"

    def scrape(self):
        # Implementation here
        pass
```

## Environment Variables

See `.env.example` for all configuration options.

## License

MIT
