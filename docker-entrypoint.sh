#!/bin/bash
set -e

# Ensure data directories exist and are writable by the scraper user.
# When host volumes are bind-mounted at /app/data or /app/config,
# the subdirectories may not exist yet or may be owned by root.
dirs=(
    /app/data
    /app/data/scraped
    /app/data/metadata
    /app/data/state
    /app/data/logs
    /app/config
    /app/config/scrapers
)

for d in "${dirs[@]}"; do
    mkdir -p "$d"
    chown scraper:scraper "$d"
done

# Ensure existing files in bind-mounted directories are writable
for f in /app/config/settings.json; do
    [ -f "$f" ] && chown scraper:scraper "$f"
done

# Drop privileges and run the main command
exec gosu scraper "$@"
