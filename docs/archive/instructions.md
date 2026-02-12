# Project: Multi-Site PDF Scraper with RAGFlow Integration

## 🎯 Project Overview
Build a modular web scraping system that downloads PDFs from multiple websites (starting with AEMO), integrates with RAGFlow for RAG ingestion, and provides an HTMX-based web interface for configuration and monitoring.

## 🏗️ Architecture Requirements

### Core Principles
- **Modular design**: Each scraper is a self-contained, pluggable module
- **Clean separation**: Scrapers, API client, orchestration, and web UI are independent
- **n8n-compatible**: All components output JSON and accept CLI arguments for future n8n integration
- **Docker-first**: Designed to run on Unraid server via Docker Compose
- **Stateless where possible**: Use file-based state tracking, no database required initially

### Technology Stack
- **Backend**: Python 3.11+
- **Web Framework**: Flask (lightweight, HTMX-friendly)
- **Frontend**: HTMX + Pure JavaScript (NO Alpine.js, NO frameworks)
- **Scraping**: Selenium + BeautifulSoup4 (hybrid approach)
- **Containerization**: Docker + Docker Compose
- **Development**: macOS local environment

## 📁 Project Structure
```
pdf-scraper/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── .dockerignore
├── .gitignore
├── README.md
│
├── app/
│   ├── __init__.py
│   ├── main.py                    # Flask application entry point
│   ├── config.py                  # Configuration management
│   │
│   ├── web/                       # HTMX Web Interface
│   │   ├── __init__.py
│   │   ├── routes.py              # Flask routes
│   │   ├── static/
│   │   │   ├── css/
│   │   │   │   └── styles.css
│   │   │   └── js/
│   │   │       ├── components.js  # Reusable HTMX components
│   │   │       └── utils.js       # Pure JS utilities
│   │   └── templates/
│   │       ├── base.html          # Base template with HTMX
│   │       ├── index.html         # Dashboard
│   │       ├── scrapers.html      # Scraper configuration
│   │       ├── logs.html          # Log viewer
│   │       └── components/        # Reusable HTMX components
│   │           ├── scraper-card.html
│   │           ├── status-badge.html
│   │           └── log-viewer.html
│   │
│   ├── scrapers/                  # Scraper modules
│   │   ├── __init__.py
│   │   ├── base_scraper.py        # Abstract base class
│   │   ├── aemo_scraper.py        # AEMO implementation
│   │   └── scraper_registry.py    # Auto-discovery of scrapers
│   │
│   ├── services/                  # External service integrations
│   │   ├── __init__.py
│   │   ├── ragflow_client.py      # RAGFlow API client
│   │   └── state_tracker.py       # State management
│   │
│   ├── orchestrator/              # Orchestration logic
│   │   ├── __init__.py
│   │   ├── scheduler.py           # Simple scheduling
│   │   └── pipeline.py            # Pipeline execution
│   │
│   └── utils/                     # Shared utilities
│       ├── __init__.py
│       ├── logging_config.py
│       └── file_utils.py
│
├── data/                          # Persistent data (mounted volume)
│   ├── scraped/                   # Downloaded PDFs
│   ├── metadata/                  # JSON metadata files
│   ├── state/                     # State tracking files
│   └── logs/                      # Application logs
│
├── config/                        # Configuration files
│   ├── scrapers/                  # Scraper-specific configs
│   │   ├── aemo.json
│   │   └── template.json
│   └── settings.json              # Global settings
│
└── scripts/                       # Utility scripts
    ├── setup.sh                   # Initial setup
    ├── run_scraper.py             # CLI runner (n8n-compatible)
    └── test_ragflow.py            # Test RAGFlow connection
```

## 🔧 Technical Requirements

### 1. Base Scraper Architecture

Create an abstract base class that all scrapers inherit from:
```python
# Key features needed in base_scraper.py:
- Abstract methods: scrape(), parse_page(), download_file()
- Built-in state tracking (check if URL already processed)
- JSON output format standardization
- CLI argument parsing
- Error handling and retry logic
- Progress reporting
- Tag-based filtering
- Metadata extraction and cleanup
```

### 2. Scraper Registry System

Implement auto-discovery of scrapers:
```python
# scraper_registry.py should:
- Scan scrapers/ directory for classes inheriting from BaseScraper
- Build registry of available scrapers
- Provide factory method: get_scraper(name) -> ScraperInstance
- Support dynamic loading of new scrapers without code changes
- Return scraper metadata (name, description, config schema)
```

### 3. RAGFlow Integration
```python
# ragflow_client.py must support:
- Create dataset
- Upload documents (batch)
- Trigger parsing
- Monitor parsing status (async polling)
- Handle authentication via Bearer token
- Comprehensive error handling
- Retry logic with exponential backoff
- Return structured results (JSON)
```

### 4. HTMX Web Interface

**Key Pages:**

1. **Dashboard** (`/`)
   - Overview of all scrapers
   - Recent activity log
   - System status
   - Quick actions (run scraper, view logs)

2. **Scrapers** (`/scrapers`)
   - List all registered scrapers
   - Configure scraper settings
   - Enable/disable scrapers
   - Set schedules
   - View scraper-specific metadata

3. **Logs** (`/logs`)
   - Real-time log viewer
   - Filter by scraper, severity, date
   - Download logs

4. **Settings** (`/settings`)
   - RAGFlow connection settings
   - Global configuration
   - Test connections

**HTMX Component Examples:**
```html
<!-- Scraper Card Component (reusable) -->
<div class="scraper-card" 
     hx-get="/scrapers/{{ scraper_name }}/status" 
     hx-trigger="every 5s"
     hx-swap="outerHTML">
  <h3>{{ scraper_name }}</h3>
  <span class="status-badge {{ status }}">{{ status }}</span>
  <button hx-post="/scrapers/{{ scraper_name }}/run"
          hx-target="closest .scraper-card"
          hx-swap="outerHTML">
    Run Now
  </button>
</div>

<!-- Status Badge Component (reusable) -->
<span class="status-badge status-{{ status }}"
      hx-get="/status/{{ item_id }}"
      hx-trigger="every 10s"
      hx-swap="outerHTML">
  {{ status_text }}
</span>

<!-- Log Viewer Component (auto-updating) -->
<div class="log-viewer"
     hx-get="/logs/stream"
     hx-trigger="every 2s"
     hx-swap="beforeend"
     hx-target="#log-container">
  <!-- Logs append here -->
</div>
```

**Pure JavaScript Requirements:**
```javascript
// components.js - Reusable HTMX enhancements
- initializeStatusPolling()
- handleScraperActions()
- updateProgressBars()
- formatLogEntries()
- showNotifications()
- confirmDangerousActions()

// NO Alpine.js, NO Vue, NO React
// Use vanilla JS with HTMX attributes for interactivity
```

### 5. Docker Configuration

**docker-compose.yml requirements:**
```yaml
services:
  scraper:
    build: .
    volumes:
      - ./data:/app/data          # Persistent storage
      - ./config:/app/config      # Configuration
      - ./logs:/app/logs          # Log files
    environment:
      - RAGFLOW_API_URL=${RAGFLOW_API_URL}
      - RAGFLOW_API_KEY=${RAGFLOW_API_KEY}
    ports:
      - "5000:5000"               # Web UI
    restart: unless-stopped
    networks:
      - scraper-net

  # Optional: ChromeDriver for Selenium
  chrome:
    image: selenium/standalone-chrome:latest
    ports:
      - "4444:4444"
    networks:
      - scraper-net

networks:
  scraper-net:
```

**Dockerfile requirements:**
```dockerfile
# Multi-stage build
# Stage 1: Dependencies
# Stage 2: Runtime with minimal footprint
# Include ChromeDriver for Selenium
# Non-root user for security
# Health check endpoint
```

### 6. CLI Interface (n8n-compatible)
```bash
# run_scraper.py must support:
python run_scraper.py --scraper aemo --output-format json
python run_scraper.py --scraper aemo --max-pages 5
python run_scraper.py --list-scrapers
python run_scraper.py --scraper aemo --upload-to-ragflow
python run_scraper.py --scraper aemo --dataset-id abc123

# Output format (JSON to stdout):
{
  "status": "completed",
  "scraper": "aemo",
  "scraped_count": 20,
  "downloaded_count": 18,
  "uploaded_count": 18,
  "failed_count": 2,
  "duration_seconds": 145.3,
  "documents": [...],
  "errors": [...]
}

# Exit codes:
# 0 = success
# 1 = failure
# 2 = partial success (some documents failed)
```

## 🎨 AEMO Scraper Implementation Details

Based on analysis of https://www.aemo.com.au/library/major-publications:

**Key Findings:**
- Pagination uses hash fragments (#e=10, #e=20, etc.) - 10 documents per page
- 22 pages total (~220 documents)
- Uses jQuery for client-side filtering
- Documents have associated tags (visible in DOM)
- No AJAX pagination - content is JavaScript-rendered on hash change
- PDF URLs follow pattern: `/-/media/files/.../document.pdf`

**Scraper Requirements:**
```python
class AEMOScraper(BaseScraper):
    """
    Required features:
    - Navigate pagination using hash fragments
    - Wait for dynamic content to load (Selenium)
    - Extract document metadata: title, date, size, tags
    - Filter by tags (EXCLUDE: Gas, Annual Report, Budget, Corporate publications)
    - Clean filenames for storage
    - Generate JSON metadata sidecars
    - Track processed URLs to avoid duplicates
    - Handle rate limiting (polite scraping)
    """
    
    # Configuration
    BASE_URL = "https://www.aemo.com.au/library/major-publications"
    EXCLUDED_TAGS = ["Gas", "Annual Report", "Budget", "Corporate publications"]
    DOCUMENTS_PER_PAGE = 10
    TOTAL_PAGES = 22
```

## 🔐 Environment Configuration
```bash
# .env.example
# RAGFlow Configuration
RAGFLOW_API_URL=http://localhost:9380
RAGFLOW_API_KEY=your_api_key_here
RAGFLOW_DATASET_ID=your_dataset_id

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=generate_random_secret_key
HOST=0.0.0.0
PORT=5000

# Selenium Configuration
SELENIUM_REMOTE_URL=http://chrome:4444/wd/hub
SELENIUM_HEADLESS=true

# Scraper Configuration
DOWNLOAD_DIR=/app/data/scraped
METADATA_DIR=/app/data/metadata
STATE_DIR=/app/data/state
LOG_DIR=/app/data/logs
MAX_CONCURRENT_DOWNLOADS=3
REQUEST_TIMEOUT=60
RETRY_ATTEMPTS=3

# Logging
LOG_LEVEL=INFO
```

## 📋 Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Project structure setup
- [ ] BaseScraper abstract class
- [ ] Scraper registry system
- [ ] State tracker implementation
- [ ] Logging configuration
- [ ] CLI interface (run_scraper.py)

### Phase 2: AEMO Scraper
- [ ] AEMO scraper implementation
- [ ] Pagination handling
- [ ] Tag filtering logic
- [ ] Metadata extraction
- [ ] Filename cleanup
- [ ] Testing with real website

### Phase 3: RAGFlow Integration
- [ ] RAGFlow client implementation
- [ ] Authentication handling
- [ ] Document upload (batch)
- [ ] Parsing trigger and monitoring
- [ ] Error handling and retries
- [ ] Testing with RAGFlow instance

### Phase 4: Web Interface
- [ ] Flask application setup
- [ ] Base template with HTMX
- [ ] Dashboard page
- [ ] Scrapers configuration page
- [ ] Log viewer
- [ ] Reusable HTMX components
- [ ] Pure JavaScript utilities
- [ ] CSS styling

### Phase 5: Orchestration
- [ ] Simple Python orchestrator
- [ ] Scheduling logic
- [ ] Pipeline execution
- [ ] Status tracking
- [ ] Web UI integration

### Phase 6: Docker & Deployment
- [ ] Dockerfile creation
- [ ] docker-compose.yml
- [ ] Volume mounting
- [ ] Network configuration
- [ ] Health checks
- [ ] Testing on macOS
- [ ] Documentation for Unraid deployment

## 🚀 Getting Started Commands
```bash
# Local development (macOS)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
python app/main.py

# Docker development
docker-compose up --build

# Run scraper manually
python scripts/run_scraper.py --scraper aemo

# Test RAGFlow connection
python scripts/test_ragflow.py

# Access web UI
open http://localhost:5000
```

## 📦 Key Dependencies
```
# requirements.txt (key packages)
flask>=3.0.0
selenium>=4.16.0
beautifulsoup4>=4.12.0
requests>=2.31.0
python-dotenv>=1.0.0
webdriver-manager>=4.0.0
lxml>=5.0.0
```

## 🎯 Success Criteria

1. ✅ Can add new scrapers by creating a single Python file in `scrapers/`
2. ✅ Web UI allows configuration without editing code
3. ✅ All scrapers output consistent JSON format
4. ✅ CLI works independently of web UI (n8n-compatible)
5. ✅ Docker container runs on Unraid
6. ✅ AEMO scraper successfully downloads and categorizes electricity documents
7. ✅ RAGFlow integration works end-to-end
8. ✅ HTMX interface is responsive and component-based
9. ✅ No Alpine.js or frontend frameworks used
10. ✅ State tracking prevents duplicate downloads

## 🔄 Future Extensibility

Design should accommodate:
- Adding new scrapers (drop in Python file)
- Switching to n8n orchestration (same CLI interface)
- Adding database (PostgreSQL) instead of file-based state
- API endpoints for external integrations
- Webhook support for real-time triggers
- Authentication and multi-user support

## 📝 Additional Context

**AEMO Website Structure:**
- Main listing page shows 10 documents at a time
- Pagination controlled via URL hash (#e=0, #e=10, #e=20...)
- Each document has: title, publication date, file size, PDF link, tags
- Tags are present in DOM but may require JavaScript inspection
- Some documents have Gas-related tags that should be excluded
- Documents are organized by date (newest first)

**RAGFlow API Endpoints:**
- POST `/api/v1/datasets` - Create dataset
- POST `/api/v1/datasets/{id}/documents` - Upload document
- POST `/api/v1/datasets/{id}/chunks` - Trigger parsing
- GET `/api/v1/datasets/{id}/documents` - Check status

Start with Phase 1 (Core Infrastructure) and build incrementally. Focus on clean abstractions and modularity from the beginning. The architecture should make it trivial to add new websites later.