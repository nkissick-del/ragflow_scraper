#!/bin/bash
set -e

# Ensure data directories exist and are writable by the scraper user.
# When host volumes are bind-mounted at /app/data or /app/config,
# the subdirectories may not exist yet or may be owned by root.
dirs=(
    /app/data/scraped
    /app/data/metadata
    /app/data/state
    /app/data/logs
    /app/config/scrapers
)

for d in "${dirs[@]}"; do
    mkdir -p "$d"
    chown scraper:scraper "$d"
done

# Drop privileges and run the main command
exec gosu scraper "$@"
