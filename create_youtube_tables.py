#!/usr/bin/env python
"""Create YouTube tables for development."""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connections

cursor = connections['default'].cursor()

# Create youtube_videos table
cursor.execute('''
CREATE TABLE IF NOT EXISTS youtube_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id VARCHAR(100) UNIQUE NOT NULL,
    titre VARCHAR(255) NOT NULL,
    description TEXT,
    vues VARCHAR(50),
    tags TEXT,
    miniature VARCHAR(255),
    niche VARCHAR(255) NOT NULL,
    region VARCHAR(50),
    scraped_at DATETIME NOT NULL
)
''')

# Create youtube_generated table
cursor.execute('''
CREATE TABLE IF NOT EXISTS youtube_generated (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    source_video_id INTEGER,
    niche VARCHAR(255),
    script TEXT,
    title VARCHAR(255),
    description TEXT,
    tags TEXT,
    video_url TEXT,
    status VARCHAR(50),
    youtube_video_id VARCHAR(100),
    youtube_url TEXT,
    approved_at DATETIME,
    posted_at DATETIME,
    created_at DATETIME
)
''')

print("✅ Tables YouTube créées avec succès en SQLite!")
