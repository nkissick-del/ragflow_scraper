# Runbook: Common Operations

Quick reference guide for day-to-day operations of the PDF Scraper system.

---

## Table of Contents

1. [Start/Stop Services](#startstop-services)
2. [Running Scrapers](#running-scrapers)
3. [Monitoring](#monitoring)
4. [Backup & Recovery](#backup--recovery)
5. [Scaling & Performance](#scaling--performance)
6. [Updates & Maintenance](#updates--maintenance)
7. [Emergency Procedures](#emergency-procedures)

---

## Start/Stop Services

### Start All Services

```bash
docker compose up -d
```

**Verify startup:**
```bash
docker compose ps
```

Expected output shows both containers as "Up":
```
NAME                  STATUS
pdf-scraper           Up
pdf-scraper-chrome    Up
```

### Stop All Services

```bash
docker compose down
```

**Note:** This stops and removes containers but preserves volumes/data.

### Stop Without Removing Containers

```bash
docker compose stop
```

### Restart All Services

```bash
docker compose restart
```

### Restart Specific Service

```bash
# Restart scraper only
docker compose restart scraper

# Restart Chrome only
docker compose restart chrome
```

### View Logs

**Follow logs (live):**
```bash
docker compose logs -f scraper
docker compose logs -f chrome
docker compose logs -f  # All services
```

**View last N lines:**
```bash
docker compose logs --tail=100 scraper
```

**View logs since timestamp:**
```bash
docker compose logs --since=2024-01-01T00:00:00 scraper
```

---

## Running Scrapers

### Via Web UI (Recommended)

1. Open http://localhost:5000
2. Navigate to scraper card
3. Click **"Run Now"** button
4. Monitor status in real-time

**Preview Mode (Dry Run):**
1. Click **"Preview"** button on scraper card
2. Reviews what would be scraped without actual downloads
3. Check results in preview panel

**Cancel Running Scraper:**
1. Click **"Cancel"** button on running scraper card
2. Scraper stops gracefully after current download

### Via Command Line

**Run specific scraper:**
```bash
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo
```

**Available options:**
```bash
--scraper SCRAPER    # Scraper name (required)
--max-pages N        # Limit pages to scrape
--dry-run            # Preview mode (no downloads)
--force              # Ignore state, scrape all
```

**Examples:**
```bash
# Run AEMO scraper with limit
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo --max-pages 5

# Dry run to preview
docker compose exec scraper \
  python scripts/run_scraper.py --scraper guardian --dry-run

# Force full re-scrape
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aer --force
```

### Check Available Scrapers

```bash
docker compose exec scraper \
  python scripts/run_scraper.py --list
```

Or check via web UI at http://localhost:5000

### View Scraper Status

**Via Web UI:**
- Dashboard shows real-time status
- Status badges: Idle, Running, Completed, Error

**Via Command Line:**
```bash
# Check state file
docker compose exec scraper \
  cat /app/data/state/aemo_state.json | jq
```

---

## Monitoring

### Web UI Dashboard

**Access:** http://localhost:5000

**Features:**
- Real-time scraper status
- Last run timestamps
- Document counts
- Quick actions (run/cancel/preview)

### Logs Page

**Access:** http://localhost:5000/logs

**Features:**
- Live log streaming
- Filter by level (INFO, WARNING, ERROR)
- Search logs
- Download log files

### Metrics Endpoint

**Access:** http://localhost:5000/metrics/pipeline

**Returns:**
- Total scrapers
- Active scrapers
- Completed runs
- Error counts
- Documents processed

### Container Health

**Check running containers:**
```bash
docker compose ps
```

**Check resource usage:**
```bash
docker stats
```

**Output shows:**
- CPU usage %
- Memory usage / limit
- Network I/O
- Disk I/O

### Application Logs

**Location:** `data/logs/scraper.log`

**View locally:**
```bash
tail -f data/logs/scraper.log
```

**Inside container:**
```bash
docker compose exec scraper tail -f /app/data/logs/scraper.log
```

**Filter by level:**
```bash
grep "ERROR" data/logs/scraper.log
grep "WARNING" data/logs/scraper.log
```

### Chrome VNC Monitoring

**Access:** http://localhost:7900  
**Password:** `<stored in team password manager>`

> ⚠️ **SECURITY WARNING:**  
> The default VNC password is `secret` and **MUST be changed before production use**.  
> Never commit passwords to documentation or version control.

**Setting/Changing VNC Password:**

1. Set the VNC password via environment variable in `docker-compose.yml`:
   ```yaml
   services:
     chrome:
       environment:
         - VNC_PASSWORD=<your-secure-password>
   ```

2. Or set it directly in the Chrome container:
   ```bash
   docker compose exec chrome sh -c "echo '<your-secure-password>' | x11vnc -storepasswd /home/seluser/.vnc/passwd"
   docker compose restart chrome
   ```

3. **Store the actual password** in your team's password manager (e.g., 1Password, LastPass, HashiCorp Vault)

**Use Cases:**
- Debug scraper browser interactions
- See what websites look like to scraper
- Troubleshoot JavaScript/rendering issues

---

## Backup & Recovery

### What to Backup

**Critical Data:**
- `data/state/` - Scraper state files (incremental tracking)
- `data/metadata/` - Document metadata
- `data/scraped/` - Downloaded documents (large)
- `config/` - Configuration files

**Optional:**
- `data/logs/` - Log files (can be large)

### Backup Commands

**Quick backup (state and metadata only):**
```bash
tar -czf backup-$(date +%Y%m%d).tar.gz \
  data/state/ \
  data/metadata/ \
  config/
```

**Full backup (includes documents):**
```bash
tar -czf backup-full-$(date +%Y%m%d).tar.gz \
  data/ \
  config/
```

**Remote backup:**
```bash
rsync -av --progress \
  data/state/ \
  data/metadata/ \
  user@backup-server:/path/to/backup/
```

### Restore Procedures

**Restore from backup:**
```bash
# Stop services
docker compose down

# Extract backup
tar -xzf backup-20260108.tar.gz

# Verify permissions
chmod -R 755 data/ config/

# Restart services
docker compose up -d
```

**Restore specific scraper state:**
```bash
# Copy state file
cp backup/data/state/aemo_state.json data/state/

# Restart scraper container
docker compose restart scraper
```

### Automated Backup Script

Create `scripts/backup.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d-%H%M%S)

# Create backup
tar -czf "$BACKUP_DIR/scraper-backup-$DATE.tar.gz" \
  data/state/ \
  data/metadata/ \
  config/

# Keep only last 7 days
find "$BACKUP_DIR" -name "scraper-backup-*.tar.gz" -mtime +7 -delete

echo "Backup completed: scraper-backup-$DATE.tar.gz"
```

**Schedule with cron:**
```bash
# Daily backup at 2 AM
0 2 * * * /path/to/scraper/scripts/backup.sh
```

---

## Scaling & Performance

### Adjust Scraper Concurrency

**Edit `.env`:**
```dotenv
MAX_CONCURRENT_DOWNLOADS=5  # Increase from 3
```

**Restart services:**
```bash
docker compose restart scraper
```

**Considerations:**
- More concurrent downloads = faster scraping
- But increases memory/CPU usage
- Target site may rate limit
- Recommended: 3-5 concurrent downloads

### Increase Container Resources

**Edit `docker-compose.yml`:**
```yaml
services:
  scraper:
    deploy:
      resources:
        limits:
          memory: 2g    # Increase from 1g
          cpus: "1.5"   # Increase from 0.75
```

**Apply changes:**
```bash
docker compose down
docker compose up -d
```

### Optimize RAGFlow Batch Sizes

RAGFlow uploads are batched for efficiency. Current default is reasonable for most cases.

**Monitor upload performance:**
```bash
grep "RAGFlow upload" data/logs/scraper.log | tail -20
```

### Clear Old Logs

**Rotate logs manually:**
```bash
# Archive old logs
mv data/logs/scraper.log data/logs/scraper.log.$(date +%Y%m%d)

# Compress archives
gzip data/logs/scraper.log.*

# Delete archives older than 30 days
find data/logs/ -name "scraper.log.*.gz" -mtime +30 -delete

# Restart to create new log
docker compose restart scraper
```

**Automate with logrotate:**

Create `/etc/logrotate.d/scraper`:
```
/path/to/scraper/data/logs/scraper.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        docker compose -f /path/to/scraper/docker-compose.yml restart scraper > /dev/null
    endscript
}
```

### Clear Old Scraped Documents

**Warning:** Only delete after confirming successful RAGFlow upload.

```bash
# Find old documents (30+ days)
find data/scraped/ -type f -mtime +30

# Delete old documents
find data/scraped/ -type f -mtime +30 -delete
```

---

## Updates & Maintenance

### Check for Updates

```bash
git fetch
git status
```

If behind:
```
Your branch is behind 'origin/main' by N commits
```

### Pull Latest Code

```bash
# Stop services
docker compose down

# Pull updates
git pull origin main

# Review changes
git log --oneline -10
```

### Rebuild Containers

**After code updates:**
```bash
# Rebuild images
docker compose build

# Start with new images
docker compose up -d
```

**Force clean rebuild:**
```bash
docker compose build --no-cache
docker compose up -d
```

### Database Migrations

**Check if migrations needed:**
```bash
docker compose exec scraper \
  python -c "from app.config import Config; print('OK')"
```

Currently no database - state stored in JSON files. Future versions may add proper database with migrations.

### Config Validation

**Validate configuration:**
```bash
docker compose exec scraper \
  python -m app.utils.config_validation
```

### Test After Update

**Quick health check:**
```bash
# Web UI responding
curl -I http://localhost:5000/

# Chrome healthy
curl http://localhost:4444/wd/hub/status

# Run test scraper
docker compose exec scraper \
  python scripts/run_scraper.py --scraper aemo --dry-run --max-pages 1
```

### Zero-Downtime Updates (Future)

Not currently supported. Updates require brief downtime:
1. Stop services: `docker compose down`
2. Pull updates: `git pull`
3. Rebuild: `docker compose build`
4. Start: `docker compose up -d`

Downtime: ~2-5 minutes

---

## Emergency Procedures

### Scraper Stuck/Hanging

**Symptoms:**
- Scraper status shows "Running" for extended period
- No log activity
- High CPU usage

**Solutions:**

1. **Cancel via web UI:**
   - Click "Cancel" button on scraper card
   - Wait 30 seconds for graceful shutdown

2. **Force restart container:**
   ```bash
   docker compose restart scraper
   ```

3. **Kill specific scraper process:**
   ```bash
   docker compose exec scraper ps aux | grep run_scraper
   docker compose exec scraper kill -9 <PID>
   ```

4. **Check state file for corruption:**
   ```bash
   docker compose exec scraper \
     cat /app/data/state/stuck_scraper_state.json
   ```
   
   If corrupted, restore from backup or delete to reset.

### RAGFlow Unreachable

**Symptoms:**
- "RAGFlow connection failed" errors
- Uploads timing out
- Documents queued but not uploaded

**Solutions:**

1. **Check RAGFlow status:**
   ```bash
   curl -I http://localhost:9380
   ```

2. **Test from scraper container:**
   ```bash
   docker compose exec scraper \
     curl -I $RAGFLOW_API_URL
   ```

3. **Verify API key:**
   - Check `.env` file
   - Test key in RAGFlow UI
   - Generate new key if expired

4. **Restart RAGFlow** (if you control it):
   ```bash
   # Depends on your RAGFlow deployment
   docker restart ragflow
   # or
   systemctl restart ragflow
   ```

5. **Disable RAGFlow temporarily:**
   - Edit `.env`: Comment out `RAGFLOW_API_URL`
   - Restart: `docker compose restart scraper`
   - Scrapers will save locally only

### Disk Full

**Symptoms:**
- Container crashes with "No space left on device"
- Cannot write logs/state
- Downloads failing

**Solutions:**

1. **Check disk usage:**
   ```bash
   df -h
   docker system df
   ```

2. **Clear Docker resources:**
   ```bash
   # Remove unused images
   docker image prune -a
   
   # Remove unused volumes
   docker volume prune
   
   # Remove build cache
   docker builder prune
   ```

3. **Clear old logs:**
   ```bash
   find data/logs/ -name "*.log.*" -delete
   ```

4. **Archive and delete old documents:**
   ```bash
   # Archive to external storage
   tar -czf archive-$(date +%Y%m%d).tar.gz data/scraped/
   mv archive-*.tar.gz /path/to/external/storage/
   
   # Delete local copies
   rm -rf data/scraped/*
   ```

5. **Increase disk space:**
   - Add new volume/disk
   - Mount to `/app/data`
   - Migrate existing data

### Memory Exhaustion

**Symptoms:**
- Container restarts with "OOMKilled"
- Very slow performance
- Chrome crashes frequently

**Solutions:**

1. **Check memory usage:**
   ```bash
   docker stats
   ```

2. **Restart services:**
   ```bash
   docker compose restart
   ```

3. **Reduce concurrency:**
   ```dotenv
   MAX_CONCURRENT_DOWNLOADS=2
   ```

4. **Increase container limits:**
   ```yaml
   # docker-compose.yml
   deploy:
     resources:
       limits:
         memory: 2g
   ```

5. **Increase Chrome shared memory:**
   ```yaml
   chrome:
     shm_size: 4gb
   ```

6. **Check for memory leaks:**
   ```bash
   docker compose logs scraper | grep -i "memory\|oom"
   ```

### Database Corruption (State Files)

**Symptoms:**
- JSON parse errors in logs
- Scraper fails to start
- "Invalid state file" errors

**Solutions:**

1. **Identify corrupted state:**
   ```bash
   # Test JSON validity
   for file in data/state/*.json; do
     echo "Testing $file"
     cat "$file" | jq . > /dev/null || echo "CORRUPTED: $file"
   done
   ```

2. **Restore from backup:**
   ```bash
   cp backup/data/state/corrupted_scraper_state.json data/state/
   ```

3. **Manual repair:**
   ```bash
   # Edit with text editor
   nano data/state/corrupted_scraper_state.json
   
   # Validate fix
   cat data/state/corrupted_scraper_state.json | jq .
   ```

4. **Reset state (last resort):**
   ```bash
   # Backup first
   mv data/state/corrupted_scraper_state.json \
      data/state/corrupted_scraper_state.json.broken
   
   # Scraper will create fresh state on next run
   docker compose restart scraper
   ```

See [MIGRATION_AND_STATE_REPAIR.md](MIGRATION_AND_STATE_REPAIR.md) for detailed state management.

### Total System Failure

**Symptoms:**
- All containers down
- Cannot start services
- Critical data loss suspected

**Recovery Steps:**

1. **Stop everything:**
   ```bash
   docker compose down -v  # WARNING: Removes volumes
   ```

2. **Restore from backup:**
   ```bash
   tar -xzf /path/to/backup/latest.tar.gz
   ```

3. **Verify data integrity:**
   ```bash
   ls -la data/state/
   ls -la data/metadata/
   ls -la config/
   ```

4. **Rebuild from scratch:**
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

5. **Verify restoration:**
   - Check web UI: http://localhost:5000
   - Run test scraper: `--dry-run`
   - Review logs for errors

---

## Quick Reference

### Most Common Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f scraper

# Run scraper
docker compose exec scraper python scripts/run_scraper.py --scraper aemo

# Check status
docker compose ps

# Restart service
docker compose restart scraper

# Check disk usage
docker system df

# Backup data
tar -czf backup.tar.gz data/state/ data/metadata/ config/
```

### Status Codes

| Status | Meaning | Action |
|--------|---------|--------|
| Idle | Ready to run | Can start scraper |
| Running | Actively scraping | Wait or cancel |
| Completed | Successfully finished | Review results |
| Error | Failed with error | Check logs, retry |
| Cancelled | User cancelled | Can restart |

---

## See Also

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Initial setup and configuration
- [SECRETS_ROTATION.md](SECRETS_ROTATION.md) - Credential rotation procedures
- [MIGRATION_AND_STATE_REPAIR.md](MIGRATION_AND_STATE_REPAIR.md) - State management details
- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Error types and handling
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Development and debugging
