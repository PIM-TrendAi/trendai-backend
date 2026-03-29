import math
import os
import re
import requests

from django.db import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.text import slugify

from ai_scripts.models import YouTubeVideo
from .models import Trend


def _bootstrap_youtube_videos_if_empty() -> None:
    try:
        if YouTubeVideo.objects.exists():
            return
    except (ProgrammingError, OperationalError):
        return

    api_key = os.getenv("YOUTUBE_API_KEY") or "AIzaSyB6siRvBv2gX01WMXvwSlK8GSZI-TN8hEA"
    if not api_key:
        return

    niche_categories = {
        "tech": "28",
        "cuisine": "26",
        "lifestyle": "22",
        "funny": "23",
    }

    for niche, category_id in niche_categories.items():
        try:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "snippet,statistics",
                    "chart": "mostPopular",
                    "regionCode": "TN",
                    "maxResults": 10,
                    "videoCategoryId": category_id,
                    "key": api_key,
                },
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            continue

        for item in payload.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            video_id = item.get("id")
            if not video_id:
                continue

            tags = snippet.get("tags") or []
            tags_text = ", ".join(tags[:12]) if isinstance(tags, list) else str(tags)

            YouTubeVideo.objects.update_or_create(
                video_id=video_id,
                defaults={
                    "titre": snippet.get("title", "Untitled"),
                    "description": snippet.get("description", ""),
                    "vues": str(stats.get("viewCount", "0")),
                    "tags": tags_text,
                    "miniature": (
                        snippet.get("thumbnails", {})
                        .get("high", {})
                        .get("url")
                    ),
                    "niche": niche,
                    "region": "TN",
                    "scraped_at": timezone.now(),
                },
            )


def _to_int(value) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else 0


def _humanize_views(views: int) -> str:
    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(views)


def _extract_hashtag(video: YouTubeVideo) -> str:
    if video.tags:
        first_tag = next((part.strip() for part in video.tags.split(",") if part.strip()), "")
        if first_tag:
            token = first_tag.replace("#", "")
            token = re.sub(r"\s+", "", token)
            if token:
                return f"#{token[:60]}"

    title_token = slugify(video.titre or "video")[:60].replace("-", "")
    return f"#{title_token or 'trend'}"


def _target_audience(niche: str) -> str:
    niche_key = (niche or "").lower()
    mapping = {
        "tech": "Tech Enthusiasts 18-40",
        "cuisine": "Food Lovers 20-45",
        "lifestyle": "Lifestyle Audience 18-35",
        "funny": "Gen Z 13-28",
    }
    return mapping.get(niche_key, "General Audience")


def _format_profile(niche: str) -> tuple[str, str]:
    niche_key = (niche or "").lower()
    if niche_key == "tech":
        return "8-15 minutes", "Review/List"
    if niche_key == "cuisine":
        return "5-12 minutes", "Recipe/Tutorial"
    if niche_key == "lifestyle":
        return "6-10 minutes", "Story/Showcase"
    if niche_key == "funny":
        return "20-60 seconds", "Short-form Comedy"
    return "3-8 minutes", "General Video"


def _build_chart(score: float) -> list[dict[str, int | str]]:
    base = max(10, int(score * 0.45))
    peak = max(base + 6, int(score))
    steps = [
        int(base * 0.82),
        int(base * 0.9),
        int(base * 0.98),
        int(base * 1.08),
        int(base * 1.16),
        peak,
        max(base, int(peak * 0.96)),
    ]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return [{"day": day, "value": max(1, val)} for day, val in zip(days, steps)]


def _compute_growth(video: YouTubeVideo) -> float:
    if video.scraped_at:
        scraped_at = video.scraped_at
        if timezone.is_naive(scraped_at):
            scraped_at = timezone.make_aware(scraped_at, timezone.get_current_timezone())
        age_hours = max(1, int((timezone.now() - scraped_at).total_seconds() // 3600))
    else:
        age_hours = 24
    freshness_bonus = max(0.0, 72.0 - min(age_hours, 72))
    views = _to_int(video.vues)
    momentum = min(140.0, math.log10(views + 1) * 22.0)
    return round(max(8.0, freshness_bonus + momentum * 0.55), 1)


def _compute_score(views: int, growth: float) -> float:
    view_component = min(72.0, math.log10(views + 1) * 12.0)
    growth_component = min(28.0, growth * 0.25)
    return round(min(99.0, max(15.0, view_component + growth_component)), 1)


def sync_scraped_youtube_to_trends(limit: int = 100) -> int:
    _bootstrap_youtube_videos_if_empty()

    try:
        videos = list(YouTubeVideo.objects.order_by("-scraped_at")[:limit])
    except (ProgrammingError, OperationalError):
        return 0

    synced = 0
    for video in videos:
        views = _to_int(video.vues)
        growth = _compute_growth(video)
        score = _compute_score(views, growth)
        avg_length, dominant_format = _format_profile(video.niche)
        hashtag = _extract_hashtag(video)

        defaults = {
            "score": score,
            "growth": growth,
            "views": _humanize_views(views),
            "type": "video",
            "analysis": [
                f"Scraped from YouTube {video.region or 'global'} trending feed",
                f"Niche: {(video.niche or 'general').title()} with high watch intent",
                "Updated automatically from n8n workflow data",
            ],
            "target_audience": _target_audience(video.niche),
            "avg_video_length": avg_length,
            "dominant_format": dominant_format,
            "best_posting_time": "6-9 PM",
            "total_views": views,
            "total_likes": int(views * 0.08),
            "total_shares": int(views * 0.02),
            "chart_data": _build_chart(score),
            "color_start": "#EF4444",
            "color_end": "#F97316",
        }

        Trend.objects.update_or_create(
            hashtag=hashtag,
            platform="YouTube",
            defaults=defaults,
        )
        synced += 1

    return synced
