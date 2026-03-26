"""
Analytics app — aggregates real TikTok data for the authenticated user.
Falls back to zeros when the user has not connected TikTok yet.
"""
from datetime import datetime, timezone, timedelta

import httpx
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from platforms.models import UserPlatform
from trends.models import SavedTrend

TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"
TIKTOK_VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/video/query/"


def _get_tiktok_token(user):
    """Return the stored TikTok access token for *user*, or None."""
    try:
        platform = UserPlatform.objects.get(user=user, platform_name="TikTok")
        return platform.access_token if platform.connected else None
    except UserPlatform.DoesNotExist:
        return None


def _tiktok_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _fetch_user_info(token):
    """Returns dict with follower_count, likes_count, video_count or None on error."""
    try:
        resp = httpx.get(
            TIKTOK_USER_INFO_URL,
            headers=_tiktok_headers(token),
            params={"fields": "follower_count,following_count,likes_count,video_count"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("user", {})
    except httpx.HTTPError:
        pass
    return None


def _fetch_all_videos(token, max_count=20):
    """Returns list of video stat dicts from TikTok, or []."""
    try:
        # Step 1: list video IDs
        resp = httpx.post(
            TIKTOK_VIDEO_LIST_URL,
            headers=_tiktok_headers(token),
            json={"max_count": max_count, "fields": ["id", "title", "create_time"]},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        video_ids = [v["id"] for v in resp.json().get("data", {}).get("videos", [])]
        if not video_ids:
            return []

        # Step 2: query stats
        resp2 = httpx.post(
            TIKTOK_VIDEO_QUERY_URL,
            headers=_tiktok_headers(token),
            json={
                "filters": {"video_ids": video_ids},
                "fields": [
                    "id", "title", "create_time",
                    "view_count", "like_count", "comment_count",
                    "share_count", "average_time_watched",
                ],
            },
            timeout=10,
        )
        if resp2.status_code == 200:
            return resp2.json().get("data", {}).get("videos", [])
    except httpx.HTTPError:
        pass
    return []


class AnalyticsSummaryView(APIView):
    """GET /api/analytics/summary/ — Overview stat cards (real TikTok data)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = _get_tiktok_token(request.user)
        if not token:
            return Response(_empty_summary())

        user_info = _fetch_user_info(token) or {}
        videos = _fetch_all_videos(token)

        followers = user_info.get("follower_count", 0)
        total_likes = user_info.get("likes_count", 0)
        total_views = sum(v.get("view_count", 0) for v in videos)
        total_comments = sum(v.get("comment_count", 0) for v in videos)
        total_shares = sum(v.get("share_count", 0) for v in videos)
        interactions = total_likes + total_comments + total_shares

        engagement = round((interactions / total_views * 100), 1) if total_views > 0 else 0.0
        viral_score = min(100, round((engagement * 0.4) + (min(total_views, 1_000_000) / 10_000)))

        return Response({
            "total_views":  _metric(total_views,  _fmt(total_views)),
            "engagement":   _metric(engagement,   f"{engagement}%"),
            "followers":    _metric(followers,     _fmt(followers)),
            "viral_score":  _metric(viral_score,   str(viral_score)),
        })


class EngagementView(APIView):
    """GET /api/analytics/engagement/ — 7-day views line chart (real TikTok data)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = _get_tiktok_token(request.user)
        if not token:
            return Response({"data": _empty_week()})

        videos = _fetch_all_videos(token, max_count=50)
        day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        today = datetime.now(tz=timezone.utc)
        buckets = {i: {"views": 0, "engagement": 0} for i in range(7)}

        for v in videos:
            ts = v.get("create_time")
            if not ts:
                continue
            created = datetime.fromtimestamp(ts, tz=timezone.utc)
            delta = (today - created).days
            if 0 <= delta < 7:
                day_idx = (today.weekday() - delta) % 7
                buckets[day_idx]["views"] += v.get("view_count", 0)
                interactions = (v.get("like_count", 0) + v.get("comment_count", 0)
                                + v.get("share_count", 0))
                views = v.get("view_count", 1)
                buckets[day_idx]["engagement"] += round(interactions / views * 100, 1)

        data = []
        for i in range(7):
            day_offset = (today - timedelta(days=6 - i))
            label = day_labels[day_offset.weekday()]
            data.append({
                "day": label,
                "views": buckets[i]["views"],
                "engagement": round(buckets[i]["engagement"], 1),
            })

        return Response({"data": data})


class PlatformPerformanceView(APIView):
    """GET /api/analytics/platforms/ — Bar chart (TikTok real, others N/A)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = _get_tiktok_token(request.user)
        tiktok_views = 0
        if token:
            videos = _fetch_all_videos(token)
            tiktok_views = sum(v.get("view_count", 0) for v in videos)

        return Response({
            "data": [
                {"name": "TikTok",    "value": tiktok_views},
                {"name": "Instagram", "value": 0},
                {"name": "YouTube",   "value": 0},
                {"name": "Facebook",  "value": 0},
            ]
        })


class HeatmapView(APIView):
    """GET /api/analytics/heatmap/ — Best posting-time heatmap."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Static engagement heatmap — real data requires TikTok Research API (enterprise)
        return Response({
            "data": [
                {"hour": "6AM",  "Mon": 2, "Tue": 3, "Wed": 4, "Thu": 5, "Fri": 8, "Sat": 9, "Sun": 7},
                {"hour": "12PM", "Mon": 5, "Tue": 6, "Wed": 7, "Thu": 8, "Fri": 9, "Sat": 8, "Sun": 6},
                {"hour": "6PM",  "Mon": 8, "Tue": 9, "Wed": 9, "Thu": 9, "Fri": 10, "Sat": 9, "Sun": 8},
                {"hour": "12AM", "Mon": 3, "Tue": 4, "Wed": 5, "Thu": 6, "Fri": 7, "Sat": 8, "Sun": 7},
            ]
        })


class SavedTrendAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        saved = SavedTrend.objects.filter(user=request.user).select_related("trend")[:10]
        return Response({
            "data": [{"name": st.trend.hashtag, "score": st.trend.score} for st in saved]
        })


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _metric(value, label, trend=None):
    return {"value": value, "label": label, "trend": trend or "—", "direction": "up"}


def _empty_summary():
    return {
        "total_views": _metric(0, "0",   "Connect TikTok"),
        "engagement":  _metric(0, "0%",  "Connect TikTok"),
        "followers":   _metric(0, "0",   "Connect TikTok"),
        "viral_score": _metric(0, "0",   "Connect TikTok"),
    }


def _empty_week():
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return [{"day": d, "views": 0, "engagement": 0} for d in days]
