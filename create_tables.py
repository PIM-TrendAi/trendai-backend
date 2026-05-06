import psycopg2

conn = psycopg2.connect(dbname='trendai_db', user='n8n', password='n8npassword', host='localhost', port='5432')
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS youtube_videos (
    id SERIAL PRIMARY KEY,
    video_id TEXT UNIQUE NOT NULL,
    titre TEXT,
    description TEXT,
    tags TEXT,
    vues BIGINT DEFAULT 0,
    niche TEXT,
    region TEXT DEFAULT 'TN',
    scraped_at TIMESTAMP DEFAULT NOW()
);
""")
print('youtube_videos table created.')

cur.execute("""
CREATE TABLE IF NOT EXISTS youtube_generated (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    source_video_id INTEGER,
    niche TEXT,
    script TEXT,
    title TEXT,
    description TEXT,
    tags TEXT,
    video_url TEXT,
    status TEXT DEFAULT 'pending_review',
    youtube_video_id TEXT,
    youtube_url TEXT,
    approved_at TIMESTAMP,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
""")
print('youtube_generated table created.')

cur.execute("""
CREATE TABLE IF NOT EXISTS facebook_reels (
    id SERIAL PRIMARY KEY,
    reel_id TEXT UNIQUE,
    reel_url TEXT,
    page_url TEXT,
    text TEXT,
    created_at TIMESTAMP,
    play_count INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    niche TEXT,
    status TEXT DEFAULT 'scraped',
    thumbnail_url TEXT,
    created_db TIMESTAMP DEFAULT NOW()
);
""")
print('facebook_reels table created.')

# Add platform column to creator_sessions if missing
cur.execute("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='creator_sessions' AND column_name='platform'
    ) THEN
        ALTER TABLE creator_sessions ADD COLUMN platform VARCHAR(50) DEFAULT 'tiktok';
    END IF;
END $$;
""")
print('creator_sessions.platform column ensured.')

cur.close()
conn.close()
