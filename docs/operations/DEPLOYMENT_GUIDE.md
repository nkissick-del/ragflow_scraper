# Deployment Guide

This guide provides complete instructions for deploying the PDF Scraper system in various environments.

---

## Table of Contents

1. [Prerequisites & System Requirements](#prerequisites--system-requirements)
2. [Environment Configuration](#environment-configuration)
3. [Docker Compose Profiles](#docker-compose-profiles)
4. [Initial Setup](#initial-setup)
5. [Service Connectivity](#service-connectivity)
6. [Common Deployment Scenarios](#common-deployment-scenarios)
7. [Troubleshooting Matrix](#troubleshooting-matrix)

---

## Prerequisites & System Requirements

### Required Software

- **Docker:** Version 24.0+ recommended
- **Docker Compose:** Version 2.20+ (V2 format required)
- **Git:** For cloning the repository

### Hardware Recommendations

**Minimum:**
- CPU: 2 cores
- RAM: 4 GB
- Disk: 20 GB free space

**Recommended (Production):**
- CPU: 4+ cores
- RAM: 8 GB+
- Disk: 50 GB+ SSD (for logs, state, scraped documents)

### Network Requirements

**Required Ports:**
- `5000` - Web UI (configurable via `PORT` env var)
- `4444` - Selenium hub (internal, optionally exposed)
- `7900` - VNC for debugging (optional, password: `secret`)

**Optional Services (if used):**
- `9380` - RAGFlow API (external service)
- `8191` - FlareSolverr (external service)

**Firewall Rules:**
- Outbound HTTPS (443) - For scraping external websites
- Outbound HTTP (80) - For some websites
- Inbound on web UI port (default 5000) - For accessing the dashboard

---

## Environment Configuration

### 1. Create Environment File

Copy the example environment file:

```bash
cp .env.example .env
```

### 2. Required Variables

Edit `.env` and configure the following:

```dotenv
# Flask Configuration
FLASK_ENV=production                    # Use 'development' for dev
FLASK_DEBUG=0                           # Set to 1 for debug mode
SECRET_KEY=GENERATE_RANDOM_SECRET_HERE  # IMPORTANT: Change this!
PORT=5000                               # Web UI port

# RAGFlow Configuration (optional)
RAGFLOW_API_URL=http://localhost:9380   # Your RAGFlow instance URL
RAGFLOW_API_KEY=your_api_key_here       # Get from RAGFlow settings
RAGFLOW_DATASET_ID=your_dataset_id      # Target dataset for uploads

# FlareSolverr Configuration (optional)
FLARESOLVERR_URL=http://localhost:8191  # Your FlareSolverr instance

# Scraper Configuration
MAX_CONCURRENT_DOWNLOADS=3              # Parallel downloads (2-5 recommended)
REQUEST_TIMEOUT=60                      # HTTP request timeout (seconds)
RETRY_ATTEMPTS=3                        # Max retry attempts for failed requests
LOG_LEVEL=INFO                          # DEBUG, INFO, WARNING, ERROR
```

### 3. Generate Secret Key

Generate a secure `SECRET_KEY` for Flask sessions:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and set it as `SECRET_KEY` in your `.env` file.

### 4. Optional API Keys

**Guardian API** (for Guardian scraper):
```dotenv
GUARDIAN_API_KEY=your_guardian_api_key
```

**OpenRouter VLM** (for visual language model processing):
```dotenv
OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY_HERE
ENABLE_VLM_PROCESSING=true
VLM_MODEL=qwen/qwen-2-vl-7b-instruct
```

### Environment-Specific Configurations

#### Development Environment
```dotenv
FLASK_ENV=development
FLASK_DEBUG=1
LOG_LEVEL=DEBUG
MAX_CONCURRENT_DOWNLOADS=2
```

#### Staging Environment
```dotenv
FLASK_ENV=production
FLASK_DEBUG=0
LOG_LEVEL=INFO
MAX_CONCURRENT_DOWNLOADS=3
```

#### Production Environment
```dotenv
FLASK_ENV=production
FLASK_DEBUG=0
LOG_LEVEL=WARNING
MAX_CONCURRENT_DOWNLOADS=5
# Use strong SECRET_KEY
# Configure proper RAGFlow credentials
# Set up log rotation
```

---

## Docker Compose Profiles

The system supports flexible deployment via Docker Compose profiles:

### Available Profiles

| Profile | Services | Use Case |
|---------|----------|----------|
| `base` (default) | Scraper + Chrome | Standalone scraper, local storage only |
| *No profiles defined yet* | Scraper + Chrome | Current default configuration |

**Note:** The current `docker-compose.yml` doesn't define explicit profiles. All services run by default. Future versions may add:
- `full` profile - Include RAGFlow + FlareSolverr as containers
- `minimal` profile - Scraper only (no Chrome for non-Selenium scrapers)

### Usage Examples

**Default (all services):**
```bash
docker compose up -d
```

**With future profiles:**
```bash
# Run with specific profile (when implemented)
docker compose --profile full up -d

# Run multiple profiles
docker compose --profile base --profile monitoring up -d
```

---

## Initial Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd scraper
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env  # or vim, code, etc.
```

Update at minimum:
- `SECRET_KEY` - Generate secure random value
- `RAGFLOW_API_URL`, `RAGFLOW_API_KEY`, `RAGFLOW_DATASET_ID` - If using RAGFlow

### 3. Create Required Directories

The application expects these directories (automatically created on first run):

```bash
mkdir -p data/{scraped,metadata,state,logs}
mkdir -p config/scrapers
```

### 4. Build Containers

```bash
docker compose build
```

**Build Options:**
```bash
# Build with no cache (clean build)
docker compose build --no-cache

# Build specific service only
docker compose build scraper
```

### 5. Start Services

```bash
docker compose up -d
```

Check service status:
```bash
docker compose ps
```

Expected output:
```
NAME                  STATUS    PORTS
pdf-scraper           Up        0.0.0.0:5000->5000/tcp
pdf-scraper-chrome    Up        0.0.0.0:4444->4444/tcp, 0.0.0.0:7900->7900/tcp
```

### 6. Verify Installation

**Web UI:** Open http://localhost:5000
- Should see scraper dashboard
- All scrapers listed

**Chrome VNC (debugging):** Open http://localhost:7900
- Password: `secret`
- Should see Chrome browser instances

**Health Checks:**
```bash
# Scraper health
curl http://localhost:5000/

# Chrome health
curl http://localhost:4444/wd/hub/status
```

### 7. Initial Configuration

1. Navigate to **Settings** page (http://localhost:5000/settings)
2. Test RAGFlow connection (if configured)
3. Test FlareSolverr connection (if configured)
4. Configure scraper-specific settings

---

## Service Connectivity

### RAGFlow Connection Test

**Via Web UI:**
1. Go to Settings → RAGFlow Configuration
2. Click "Test Connection"
3. Should see "✓ Connection successful"

**Via Command Line:**
```bash
curl -sS --fail \
  -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:9380/api/v1/datasets
```

Expected: JSON response with datasets list

**Common Issues:**
- **Connection refused:** RAGFlow not running or wrong URL
- **401 Unauthorized:** Invalid API key
- **404 Not Found:** Wrong API endpoint version

### FlareSolverr Connection Test

**Via Web UI:**
1. Go to Settings → FlareSolverr Configuration
2. Click "Test Connection"
3. Should see "✓ Connection successful"

**Via Command Line:**
```bash
curl -X POST http://localhost:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{"cmd":"sessions.list"}'
```

Expected: JSON response with sessions list

**Common Issues:**
- **Connection refused:** FlareSolverr not running
- **Timeout:** FlareSolverr overloaded, increase timeout

### Network Troubleshooting

**DNS Resolution:**
```bash
docker compose exec scraper nslookup google.com
```

**Proxy Check (if using proxy):**
```bash
docker compose exec scraper curl -I https://www.google.com
```

**Container Network:**
```bash
# Check network connectivity between containers
docker compose exec scraper ping chrome
```

**Port Conflicts:**
```bash
# Check if ports are already in use
lsof -i :5000
lsof -i :4444
lsof -i :7900
```

---

## Common Deployment Scenarios

### Scenario 1: Local Development

**Configuration:**
```dotenv
FLASK_ENV=development
FLASK_DEBUG=1
LOG_LEVEL=DEBUG
RAGFLOW_API_URL=http://localhost:9380
FLARESOLVERR_URL=http://localhost:8191
```

**Commands:**
```bash
docker compose up  # No -d for log visibility
```

**Access:**
- Web UI: http://localhost:5000
- Chrome VNC: http://localhost:7900
- Logs: Terminal output

### Scenario 2: Production Server

**Configuration:**
```dotenv
FLASK_ENV=production
FLASK_DEBUG=0
LOG_LEVEL=WARNING
SECRET_KEY=<64-character-random-hex>
PORT=5000
```

**Commands:**
```bash
docker compose up -d
docker compose logs -f scraper  # Monitor logs
```

**Recommendations:**
- Use reverse proxy (nginx/Traefik) for HTTPS
- Enable log rotation
- Set up monitoring (health checks)
- Regular backups of `data/` directory

### Scenario 3: Running Without RAGFlow (Local Storage Only)

**Configuration:**
```dotenv
# Leave RAGFlow variables empty or commented
# RAGFLOW_API_URL=
# RAGFLOW_API_KEY=
# RAGFLOW_DATASET_ID=
```

**Behavior:**
- Scrapers will download and save files to `data/scraped/`
- Metadata saved to `data/metadata/`
- No automatic RAGFlow uploads
- Can manually upload later

**Use Case:** Testing scrapers, offline development, local archival

### Scenario 4: Running Without FlareSolverr (No Cloudflare Bypass)

**Configuration:**
```dotenv
# Leave FlareSolverr empty or commented
# FLARESOLVERR_URL=
```

**Behavior:**
- Scrapers will use direct HTTP requests
- Cloudflare-protected sites may fail
- Toggle cloudflare bypass per scraper in web UI

**Use Case:** Sites without Cloudflare protection, reduce service dependencies

---

## Troubleshooting Matrix

### Container Won't Start

**Symptoms:**
- `docker compose up` fails
- Container exits immediately
- Error: "port already allocated"

**Solutions:**

1. **Check logs:**
   ```bash
   docker compose logs scraper
   docker compose logs chrome
   ```

2. **Port conflicts:**
   ```bash
   # Change port in .env
   PORT=5001
   docker compose up -d
   ```

3. **Environment variables:**
   ```bash
   # Verify .env is loaded
   docker compose config | grep FLASK_ENV
   ```

4. **Rebuild containers:**
   ```bash
   docker compose down
   docker compose build --no-cache
   docker compose up -d
   ```

### Can't Connect to RAGFlow

**Symptoms:**
- "Connection failed" in Settings
- Scraper errors: "RAGFlow unreachable"
- Timeout errors

**Solutions:**

1. **Verify RAGFlow is running:**
   ```bash
   curl -I http://localhost:9380
   ```

2. **Check API key:**
   - Log into RAGFlow UI
   - Settings → API Keys
   - Generate new key if expired

3. **Network connectivity:**
   
   **Docker Desktop (macOS/Windows):**
   ```bash
   docker compose exec scraper curl -I http://host.docker.internal:9380
   ```
   
   If RAGFlow is on host, use:
   ```dotenv
   RAGFLOW_API_URL=http://host.docker.internal:9380
   ```
   
   **Linux:**
   `host.docker.internal` is not available on Linux. Use one of these alternatives:
   
   - **Option 1: Use Docker bridge gateway IP (usually 172.17.0.1):**
     ```bash
     docker compose exec scraper curl -I http://172.17.0.1:9380
     ```
     ```dotenv
     RAGFLOW_API_URL=http://172.17.0.1:9380
     ```
   
   - **Option 2: Use host machine's actual IP:**
     ```bash
     # Find your host IP
     ip addr show docker0 | grep inet
     # Or use your machine's network IP
     hostname -I | awk '{print $1}'
     
     # Test connectivity (replace <HOST_IP> with actual IP)
     docker compose exec scraper curl -I http://<HOST_IP>:9380
     ```
     ```dotenv
     RAGFLOW_API_URL=http://<HOST_IP>:9380
     ```
   
   - **Option 3: Use host network mode (simplest for local development):**
     In `docker-compose.yml`, change:
     ```yaml
     services:
       scraper:
         network_mode: "host"
     ```
     Then use:
     ```dotenv
     RAGFLOW_API_URL=http://localhost:9380
     ```

4. **Firewall rules:**
   - Ensure RAGFlow port (9380) is accessible
   - Check Docker network: `docker network inspect scraper_scraper-net`

### FlareSolverr Timeout

**Symptoms:**
- Scraper hangs on Cloudflare-protected sites
- Error: "FlareSolverr request timeout"
- Very slow scraping

**Solutions:**

1. **Increase timeout:**
   ```dotenv
   REQUEST_TIMEOUT=120  # Increase from 60
   ```

2. **Check FlareSolverr status:**
   ```bash
   curl http://localhost:8191/v1 \
     -X POST \
     -H "Content-Type: application/json" \
     -d '{"cmd":"sessions.list"}'
   ```

3. **Restart FlareSolverr:**
   ```bash
   # If running as separate service
   docker restart flaresolverr
   ```

4. **Disable for specific scraper:**
   - Go to Scraper card in UI
   - Toggle "Cloudflare Bypass" to OFF

### Permission Errors

**Symptoms:**
- "Permission denied" writing to `/app/data`
- Can't create state files
- Log files not created

**Solutions:**

1. **Check volume ownership:**
   ```bash
   ls -la data/
   ```

2. **Fix permissions:**
   ```bash
   sudo chown -R $(id -u):$(id -g) data/ logs/ config/
   chmod -R 755 data/ logs/ config/
   ```

3. **SELinux (if applicable):**
   ```bash
   chcon -Rt svirt_sandbox_file_t data/ logs/ config/
   ```

### Out of Memory

**Symptoms:**
- Container restarts frequently
- OOMKilled in logs
- Slow performance
- Browser crashes

**Solutions:**

1. **Increase container memory:**
   
   Edit `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 2g  # Increase from 1g
         cpus: "1.0"
   ```

2. **Reduce concurrent downloads:**
   ```dotenv
   MAX_CONCURRENT_DOWNLOADS=2  # Reduce from 3
   ```

3. **Increase Chrome shared memory:**
   ```yaml
   chrome:
     shm_size: 4gb  # Increase from 2gb
   ```

4. **Check system resources:**
   ```bash
   docker stats
   ```

### Scraper Errors

**Symptoms:**
- Scraper fails to download documents
- HTTP errors (404, 403, 500)
- Timeout errors

**Solutions:**

1. **Check scraper logs:**
   ```bash
   docker compose exec scraper tail -f /app/data/logs/scraper.log
   ```

2. **Dry run mode:**
   ```bash
   docker compose exec scraper \
     python scripts/run_scraper.py --scraper aemo --dry-run
   ```

3. **Increase retries:**
   ```dotenv
   RETRY_ATTEMPTS=5  # Increase from 3
   REQUEST_TIMEOUT=90  # Increase timeout
   ```

4. **Check target website:**
   - Website may be down
   - Structure may have changed
   - Rate limiting may be in effect

### Chrome Connection Failed

**Symptoms:**
- "Failed to connect to Selenium"
- Chrome container unhealthy
- VNC shows no browser

**Solutions:**

1. **Restart Chrome:**
   ```bash
   docker compose restart chrome
   ```

2. **Check Chrome health:**
   ```bash
   curl http://localhost:4444/wd/hub/status
   ```

3. **Increase Chrome startup time:**
   
   Edit `docker-compose.yml`:
   ```yaml
   healthcheck:
     start_period: 30s  # Increase from 10s
   ```

4. **Check Chrome logs:**
   ```bash
   docker compose logs chrome
   ```

---

## Production Checklist

Before deploying to production:

- [ ] Generate strong `SECRET_KEY`
- [ ] Set `FLASK_ENV=production` and `FLASK_DEBUG=0`
- [ ] Configure proper `LOG_LEVEL` (WARNING or ERROR)
- [ ] Set up HTTPS reverse proxy (nginx/Traefik)
- [ ] Enable authentication (if needed)
- [ ] Configure log rotation
- [ ] Set up automated backups of `data/` directory
- [ ] Configure monitoring/health checks
- [ ] Test RAGFlow connectivity
- [ ] Test FlareSolverr connectivity (if used)
- [ ] Document service account credentials
- [ ] Set up proper firewall rules
- [ ] Configure resource limits appropriately
- [ ] Test disaster recovery procedures

---

## Next Steps

- **Operations:** See [RUNBOOK_COMMON_OPERATIONS.md](RUNBOOK_COMMON_OPERATIONS.md)
- **State Management:** See [MIGRATION_AND_STATE_REPAIR.md](MIGRATION_AND_STATE_REPAIR.md)
- **Development:** See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
- **Architecture:** See [CONFIG_AND_SERVICES.md](CONFIG_AND_SERVICES.md)

---

## Support

For issues not covered in this guide:
- Check `data/logs/scraper.log` for detailed error messages
- Review [ERROR_HANDLING.md](ERROR_HANDLING.md) for error types
- Consult [ragflow_scraper_audit.md](ragflow_scraper_audit.md) for RAGFlow-specific issues
