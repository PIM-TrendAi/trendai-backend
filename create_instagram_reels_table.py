"""
One-shot script: creates the instagram_reels table in the same PostgreSQL DB
that n8n and Django share.  Run once, then you can delete this file.

Usage:
    python create_instagram_reels_table.py
"""
import os, sys
from pathlib import Path

# Load Django .env so we can read DB_* vars
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import psycopg2

conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME", "trendai_db"),
    user=os.getenv("DB_USER", "n8n"),
    password=os.getenv("DB_PASSWORD", "n8npassword"),
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5433"),
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS instagram_reels (
    id              BIGSERIAL PRIMARY KEY,
    reel_id         TEXT UNIQUE NOT NULL,
    reel_url        TEXT,
    thumbnail_url   TEXT,
    caption         TEXT,
    author          TEXT,
    views           BIGINT DEFAULT 0,
    likes           BIGINT DEFAULT 0,
    niche           TEXT,
    hashtags        TEXT,
    scraped_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Speed up niche filtering
CREATE INDEX IF NOT EXISTS idx_instagram_reels_niche
    ON instagram_reels (niche);

-- Speed up ordering
CREATE INDEX IF NOT EXISTS idx_instagram_reels_scraped_views
    ON instagram_reels (scraped_at DESC, views DESC);
""")

print("OK - instagram_reels table created successfully!")
cur.close()
conn.close()
