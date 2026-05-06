CREATE TABLE IF NOT EXISTS threads_posts (
  id SERIAL PRIMARY KEY,
  post_id TEXT UNIQUE NOT NULL,
  post_url TEXT,
  profile_url TEXT,
  username TEXT,
  text TEXT,
  created_at TIMESTAMP,
  like_count INT DEFAULT 0,
  reply_count INT DEFAULT 0,
  repost_count INT DEFAULT 0,
  has_video BOOLEAN DEFAULT FALSE,
  video_url TEXT,
  thumbnail_url TEXT,
  niche TEXT,
  status TEXT DEFAULT 'scraped'
);

CREATE TABLE IF NOT EXISTS threads_generated_videos (
  id SERIAL PRIMARY KEY,
  post_id TEXT,
  user_id TEXT,
  session_id TEXT,
  niche TEXT,
  user_prompt TEXT,
  script TEXT,
  script_text TEXT,
  video_url TEXT,
  status TEXT DEFAULT 'processing'
);
