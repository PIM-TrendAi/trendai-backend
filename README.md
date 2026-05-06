# TrendAI Backend

Django REST API powering the TrendAI platform — a multi-platform trend discovery and AI-powered video generation system for TikTok, Instagram, Facebook, YouTube, and Threads.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Django 4.2 + Django REST Framework |
| Auth | JWT (SimpleJWT) — email-based, no username |
| Database | PostgreSQL 15 |
| Async / WebSocket | Django Channels + Daphne |
| Workflow Automation | N8N (webhook-based) |
| AI (scripts) | Groq llama-3.3-70b via N8N |
| Video Generation | Fal.ai via N8N |
| API Docs | drf-spectacular (Swagger UI) |

---

## Project Structure

```
trendai-backend/
├── config/                  # Settings, URL root, ASGI, Channels routing
├── accounts/                # Custom user model, JWT auth, password reset
├── platforms/               # TikTok / Instagram / Facebook / YouTube / Threads connections
├── trends/                  # Hashtag & video trends, user bookmarks, N8N-managed content
├── analytics/               # Real-time platform analytics (TikTok, Instagram, Facebook)
├── ai_scripts/              # AI script generation endpoint
├── n8n_integration/         # Webhook bridge: sessions, script/video approval, callbacks
├── scratch/                 # Debug/utility scripts (not for production)
├── docker-compose.yaml      # PostgreSQL + N8N services
├── Dockerfile.n8n           # N8N container config
├── requirements.txt
└── manage.py
```

---

## Django Apps

| App | Responsibility |
|-----|----------------|
| `accounts` | User registration, login, JWT tokens, profile, password reset, reCAPTCHA |
| `platforms` | OAuth/token management for all 5 platforms, WebSocket consumers |
| `trends` | Trend listing/filtering/bookmarking, N8N-managed scraped content (FacebookReel, YouTubeVideo, ThreadsPost) |
| `analytics` | Summary cards, 7-day engagement charts, posting-time heatmap, Instagram/Facebook live stats |
| `ai_scripts` | Prompt-based script generation (hook / body / CTA / hashtags) |
| `n8n_integration` | Session management, trending video storage, script/video approval, N8N webhook callbacks |

---

## API Endpoints

### Authentication — `/api/auth/`
| Method | Path | Description |
|--------|------|-------------|
| POST | `/register/` | Register (reCAPTCHA required) |
| POST | `/login/` | Get JWT access + refresh tokens |
| POST | `/refresh/` | Rotate access token |
| GET/PATCH | `/profile/` | Get or update profile |
| POST | `/password-reset/` | Request reset email |
| POST | `/password-reset/confirm/` | Confirm reset with token |

### Platforms — `/api/platforms/`
- `GET /` — All platform connection statuses
- TikTok, Instagram, Facebook, YouTube, Threads: `connect`, `disconnect`, `status`, `oauth/start`, `oauth/callback`

### Trends — `/api/trends/`
- `GET /` — List trends (`?platform=`, `?sort=growth|score|views`, `?niche=`)
- `POST /{id}/save/` / `DELETE /{id}/save/` — Bookmark management
- `GET /saved/` — Saved trends
- `GET /reels/` / `GET /youtube-videos/` / `GET /threads-posts/` — N8N-scraped content
- `POST /facebook-scrape/` / `POST /youtube-scrape/` / `POST /threads-scrape/` — Trigger scraping

### Analytics — `/api/analytics/`
- `GET /summary/` — Overview cards
- `GET /engagement/` — 7-day views chart
- `GET /heatmap/` — Best posting-time heatmap
- `GET /instagram/` / `GET /facebook/` — Live platform stats

### N8N Integration — `/api/n8n/`
- `POST /start/` — Start workflow session
- `GET /sessions/{session_id}/` — Session status
- `POST /approve/script/` / `POST /approve/video/` — Approve or decline
- `GET /trending_videos/` / `GET /instagram-reels/` / `GET /facebook_reels/`
- `POST /callback/` — Receive results from N8N

### AI Scripts — `/api/scripts/`
- `GET /` — Saved scripts
- `POST /generate/` — Generate script

### System
- `GET /api/health/` — Health check
- `GET /api/docs/` — Swagger UI

---

## Authentication

- **JWT Bearer tokens** — `Authorization: Bearer <access_token>`
- Access token TTL: 60 min (configurable), Refresh token TTL: 7 days
- Refresh tokens rotate on every use
- Internal N8N ↔ Django calls use a shared `X-Internal-Secret` header

---

## Platform Integrations

| Platform | Integration |
|----------|-------------|
| TikTok | OAuth via N8N, `/v2/user/info/`, `/v2/video/list/`, `/v2/video/query/` |
| Instagram | Graph API v21.0 — media, insights, profile |
| Facebook | Graph API v24.0 — page info, posts, impressions, video views; full OAuth flow |
| YouTube | N8N-scraped content, OAuth endpoints |
| Threads | N8N-scraped content, OAuth endpoints |
| N8N | Webhook triggers (scrape, generate); receives callbacks at `/api/n8n/callback/` |
| Groq | llama-3.3-70b for Facebook script generation |
| Fal.ai | Video generation (invoked from N8N) |
| Gmail SMTP | Password reset emails |
| reCAPTCHA v2 | Register + password reset protection |

---

## Database

**PostgreSQL 15** — database name `trendai_db`

**Django-managed tables:** `users`, `user_platforms`, `trends`, `saved_trends`, `ai_scripts`, `trending_videos`, `creator_sessions`, `generated_scripts`, `generated_videos`, `facebook_generated_videos`, `posted_videos`, `instagram_reels`, `workflow_runs`

**N8N-managed (Django read-only, `managed=False`):** `facebook_reels`, `youtube_videos`, `threads_posts`

---

## Environment Variables

Create a `.env` file at the project root:

```env
# Django
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=trendai_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# JWT
ACCESS_TOKEN_LIFETIME_MINUTES=60
REFRESH_TOKEN_LIFETIME_DAYS=7

# N8N
N8N_WEBHOOK_BASE_URL=https://your-ngrok-url
INTERNAL_API_SECRET=your-internal-secret
N8N_CALLBACK_SECRET=your-callback-secret
DJANGO_CALLBACK_BASE_URL=http://localhost:8000

# N8N Webhook Paths
N8N_FACEBOOK_START_WEBHOOK_PATH=facebook-start
N8N_FACEBOOK_SCRAPE_WEBHOOK_PATH=facebook-scrape
N8N_YOUTUBE_START_WEBHOOK_PATH=youtube-start
N8N_YOUTUBE_SCRAPE_WEBHOOK_PATH=youtube-scrape

# Social Platforms
INSTAGRAM_ACCESS_TOKEN=
IG_BUSINESS_ACCOUNT_ID=
FACEBOOK_ACCESS_TOKEN=
FACEBOOK_PAGE_ID=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_REDIRECT_URI=

# AI / LLM
GROQ_API_KEY=

# Email
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Security
RECAPTCHA_SECRET_KEY=
CORS_ALLOWED_ORIGINS=http://localhost:8080
```

---

## Local Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 4. Run database migrations
python manage.py migrate

# 5. (Optional) Seed initial trend data
python manage.py seed_data

# 6. Create admin user
python manage.py createsuperuser

# 7. Start the server (ASGI for WebSocket support)
daphne -p 8000 config.asgi:application
```

- API: http://localhost:8000/api/
- Swagger docs: http://localhost:8000/api/docs/
- Admin panel: http://localhost:8000/admin/
- Health check: http://localhost:8000/api/health/

---

## Docker (PostgreSQL + N8N)

```bash
docker-compose up -d
```

- PostgreSQL: `localhost:5433`
- N8N: http://localhost:5678
- Django still runs separately (`daphne` command above)

---

## WebSocket Endpoints

| Path | Consumer |
|------|----------|
| `ws://localhost:8000/ws/tiktok-stats/` | TikTokStatsConsumer |
| `ws://localhost:8000/ws/facebook-stats/` | FacebookStatsConsumer |

---

## N8N Webhook Paths

| Platform | Webhook Path |
|----------|-------------|
| TikTok (start) | `205b7271-5246-4e81-80b4-7b93579ab006` |
| TikTok (scrape) | `8a4b64f3-ac29-4591-a1b7-4c2089f92bb4` |
| Instagram | `instagram-start` / `instagram-scrape` |
| Facebook | `facebook-start` / `facebook-scrape` |
| YouTube | configurable via `.env` |
| Threads | configurable via `.env` |

---

## Key Design Decisions

- **N8N as external processor** — trend scraping, script generation, and video generation all happen inside N8N; Django only stores and serves the results
- **`managed=False` models** — tables owned by N8N are mapped read-only in Django ORM
- **Stateless JWT** — no server-side sessions
- **Custom exception handler** — all errors return consistent `{ "error": "...", "details": "..." }` JSON
- **Pagination** — 20 items per page by default (DRF `PageNumberPagination`)
