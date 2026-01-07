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

### Production Deployment

For detailed deployment instructions, see **[DEPLOYMENT_GUIDE.md](docs/operations/DEPLOYMENT_GUIDE.md)**.

**Quick setup:**

```bash
# 1. Clone and configure
git clone <repository-url>
cd scraper
cp .env.example .env
nano .env  # Configure SECRET_KEY, RAGFlow, etc.

# 2. Build and start
docker compose build
docker compose up -d

# 3. Access web UI
open http://localhost:5000
```

**Docker Compose Profiles:**

```bash
# Default: All services (scraper + Chrome)
docker compose up -d

# Future profiles (when implemented):
# docker compose --profile full up -d      # Include RAGFlow/FlareSolverr
# docker compose --profile minimal up -d   # Scraper only
```

See [DEPLOYMENT_GUIDE.md](docs/operations/DEPLOYMENT_GUIDE.md) for:

- Environment configuration
- Service connectivity tests
- Troubleshooting guide
- Production best practices

### Day-to-Day Operations

For day-to-day operations, see **[RUNBOOK_COMMON_OPERATIONS.md](docs/operations/RUNBOOK_COMMON_OPERATIONS.md)**.

**Common commands:**

```bash
# Start/stop services
docker compose up -d
docker compose down

# View logs
docker compose logs -f scraper

# Run scraper
docker compose exec scraper python scripts/run_scraper.py --scraper aemo

# Backup data
tar -czf backup.tar.gz data/state/ data/metadata/ config/
```

### Dev Workflow (Make + dev compose)

These targets default to `docker-compose.dev.yml` and run everything inside the dev container.

```bash
# Build and run the dev stack
make dev-build
make dev-up

# Logs and shell
make logs
make shell

# Tests
make test          # all tests
make test-unit     # unit tests only
make test-int      # integration tests only
make test-file FILE=tests/unit/test_metadata_validation.py::TestClass::test_case

# Optional: override compose file (defaults to docker-compose.dev.yml)
make dev-up COMPOSE=docker-compose.yml
```

Notes:

- Dev web UI: <http://localhost:5001> (mapped from container 5000).
- VS Code tasks mirror these targets (Terminal → Run Task).

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

Access the web UI at <http://localhost:5000>

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

### Validation and maintenance

```bash
# Validate state files (read-only)
python scripts/run_scraper.py state validate

# Repair state files and write sanitized copies
python scripts/run_scraper.py state repair --write

# Validate settings.json and scraper configs
python scripts/run_scraper.py config validate

# Migrate settings/scraper configs to defaults/schema and write back
python scripts/run_scraper.py config migrate --write
```

> Tip: when running locally outside Docker, override dirs to avoid `/app` defaults, e.g. `DOWNLOAD_DIR=./data/scraped STATE_DIR=./data/state`.

## Project Structure

```tree
scraper/
├── app/
│   ├── scrapers/       # Scraper modules
│   ├── services/       # External integrations (RAGFlow, FlareSolverr)
│   ├── orchestrator/   # Scheduling and pipelines
│   ├── web/            # Flask web interface (blueprints-based)
│   └── utils/          # Shared utilities
├── config/             # Configuration files
│   ├── settings.json   # Runtime settings
│   └── scrapers/       # Per-scraper configurations
├── data/               # Runtime data
│   ├── scraped/        # Downloaded documents
│   ├── metadata/       # Document metadata
│   ├── state/          # Scraper state files
│   └── logs/           # Application logs
├── docs/               # Documentation
│   ├── DEPLOYMENT_GUIDE.md              # Production deployment
│   ├── RUNBOOK_COMMON_OPERATIONS.md     # Day-to-day operations
│   ├── MIGRATION_AND_STATE_REPAIR.md    # State management
│   ├── DEVELOPER_GUIDE.md               # Development guide (see below)
│   └── ...
├── scripts/            # CLI tools and utilities
└── docker-compose.yml  # Production compose file
```

## Adding a New Scraper

For detailed instructions, see **[DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)**.

**Quick start:**

1. Create a new file in `app/scrapers/` (e.g., `my_scraper.py`)
2. Inherit from `BaseScraper` and implement required methods
3. The scraper will be auto-discovered and available via CLI and web UI

```python
from app.scrapers.base_scraper import BaseScraper

class MyScraper(BaseScraper):
    NAME = "my-scraper"
    DESCRIPTION = "Scrapes documents from example.com"

    def scrape(self):
        # Implementation here
        pass
    
    def get_metadata(self, filepath):
        # Extract document metadata
        return {
            "title": "Document title",
            "source": "my-scraper",
            "url": "https://example.com/doc.pdf"
        }
```

See [DEVELOPER_GUIDE.md](docs/development/DEVELOPER_GUIDE.md) for:

- Development setup
- Scraper best practices
- Testing and debugging
- Architecture overview

## Documentation

### Operations

- **[Deployment Guide](docs/operations/DEPLOYMENT_GUIDE.md)** - Production deployment, Docker setup, service configuration
- **[Runbook - Common Operations](docs/operations/RUNBOOK_COMMON_OPERATIONS.md)** - Daily operations, troubleshooting, maintenance tasks
- **[Migration & State Repair](docs/operations/MIGRATION_AND_STATE_REPAIR.md)** - State file management, recovery procedures
- **[Troubleshooting: RAGFlow](docs/operations/troubleshooting/ragflow_scraper_audit.md)** - RAGFlow integration issues and fixes

### Development

- **[Developer Guide](docs/development/DEVELOPER_GUIDE.md)** - Development setup, scraper architecture, best practices
- **[Example Scraper Walkthrough](docs/development/EXAMPLE_SCRAPER_WALKTHROUGH.md)** - Step-by-step guide to creating a new scraper
- **[Configuration & Services](docs/development/CONFIG_AND_SERVICES.md)** - Configuration system, service integration patterns
- **[Error Handling & Logging](docs/development/ERROR_HANDLING.md)** - Exception hierarchy, retry patterns, logging standards

### Reference

- **[Metadata Schema](docs/reference/METADATA_SCHEMA.md)** - Document metadata structure and validation
- **[Changelog](docs/CHANGELOG.md)** - Version history and release notes

## Environment Variables

See `.env.example` for all configuration options.

### Authentication (optional)

- Enable basic auth on the web UI by setting `BASIC_AUTH_ENABLED=true` and providing `BASIC_AUTH_USERNAME` / `BASIC_AUTH_PASSWORD`.
- Leave disabled for local development (default).

### Logging

- File logs default to JSON lines with size-based rotation (10 MB, 5 backups). Configure via:
  - `LOG_JSON_FORMAT` (true/false)
  - `LOG_FILE_MAX_BYTES` (bytes)
  - `LOG_FILE_BACKUP_COUNT` (files to keep)
  - `LOG_TO_FILE` (toggle file output)
  - `LOG_LEVEL` (INFO, DEBUG, etc.)

### Config precedence

- Secrets and endpoints come from `.env` (environment variables).
- Runtime-tunable behavior (timeouts, defaults, per-scraper overrides) lives in `config/settings.json` and is validated against an internal JSON schema at load/save time.
- When in doubt: `.env` wins for secrets/URLs; `settings.json` wins for UI-tuned behavior.

### Security/HTTPS

- Always terminate TLS in front of the app (e.g., nginx/Traefik with valid certs) when exposed off-LAN.
- Enable `BASIC_AUTH_ENABLED` + credentials for the UI whenever it is reachable outside trusted networks.
- Keep secrets in `.env` (not in `settings.json`); rotate keys regularly and scope API keys per-environment.
- If running behind a proxy, set forwarded headers correctly (X-Forwarded-Proto/Host) and prefer HSTS at the proxy layer.
- When behind a reverse proxy, set `TRUST_PROXY_COUNT` (e.g., 1 for a single proxy hop) so Flask respects forwarded host/proto via ProxyFix.
- Quick checklist: TLS terminated at proxy with HSTS; `BASIC_AUTH_ENABLED=true` with strong creds if exposed; `TRUST_PROXY_COUNT` set when proxied; secrets only in `.env`; restrict writeable volumes (`config/`, `data/`, `logs/`) to trusted hosts.
- Restrict write volumes (`config/`, `data/`, `logs/`) to least privilege; avoid sharing these into untrusted containers.
- Example Traefik snippet (secure headers + forwarded proto):

    ```yaml
    labels:
        - traefik.enable=true
        - traefik.http.routers.scraper.rule=Host(`scraper.example.com`)
        - traefik.http.routers.scraper.entrypoints=websecure
        - traefik.http.routers.scraper.tls.certresolver=letsencrypt
        - traefik.http.middlewares.scraper-headers.headers.stsSeconds=31536000
        - traefik.http.middlewares.scraper-headers.headers.forceSTSHeader=true
        - traefik.http.middlewares.scraper-headers.headers.stsIncludeSubdomains=true
        - traefik.http.middlewares.scraper-headers.headers.stsPreload=true
        - traefik.http.middlewares.scraper-headers.headers.referrerPolicy=same-origin
        - traefik.http.routers.scraper.middlewares=scraper-headers
    ```

## Running Tests

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest tests/unit -v --cov=app
```

Integration tests are skipped by default; set `RUN_INTEGRATION_TESTS=1` to enable them. Integration runs may require network access and Selenium services.

Security scan:

```bash
pip install -r requirements-dev.txt
pip-audit
```

## License

MIT
