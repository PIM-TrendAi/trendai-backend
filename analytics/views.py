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


def _fetch_all_videos_debug(token):
    """Returns raw step-by-step responses for debugging."""
    out = {}
    try:
        r1 = httpx.post(TIKTOK_VIDEO_LIST_URL, headers=_tiktok_headers(token),
                        params={"fields": "id,title,create_time,cover_image_url,share_url"},
                        json={"max_count": 5}, timeout=10)
        out["list_status"] = r1.status_code
        out["list_body"] = r1.json()
        ids = [v["id"] for v in r1.json().get("data", {}).get("videos", [])]
        if ids:
            r2 = httpx.post(TIKTOK_VIDEO_QUERY_URL, headers=_tiktok_headers(token),
                            params={"fields": "id,title,view_count,like_count,comment_count,share_count"},
                            json={"filters": {"video_ids": ids}}, timeout=10)
            out["query_status"] = r2.status_code
            out["query_body"] = r2.json()
    except Exception as e:
        out["exception"] = str(e)
    return out


def _fetch_all_videos(token, max_count=20):
    max_count = min(max_count, 20)  # TikTok API hard limit
    """Returns list of video stat dicts from TikTok, or []."""
    try:
        # Step 1: list video IDs + create_time (only available from video/list)
        resp = httpx.post(
            TIKTOK_VIDEO_LIST_URL,
            headers=_tiktok_headers(token),
            params={"fields": "id,title,create_time,cover_image_url,share_url"},
            json={"max_count": max_count},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        list_videos = resp.json().get("data", {}).get("videos", [])
        if not list_videos:
            return []

        # Build lookup for create_time by video ID
        meta = {v["id"]: v for v in list_videos}
        video_ids = list(meta.keys())

        # Step 2: query stats (create_time is NOT a valid field here)
        resp2 = httpx.post(
            TIKTOK_VIDEO_QUERY_URL,
            headers=_tiktok_headers(token),
            params={"fields": "id,title,view_count,like_count,comment_count,share_count"},
            json={"filters": {"video_ids": video_ids}},
            timeout=10,
        )
        if resp2.status_code != 200:
            return []

        # Merge stats with create_time from step 1
        stats = resp2.json().get("data", {}).get("videos", [])
        for v in stats:
            m = meta.get(v["id"], {})
            v["create_time"] = m.get("create_time")
            v.setdefault("cover_image_url", m.get("cover_image_url", ""))
            v["share_url"] = m.get("share_url", "")
        return stats
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

        videos = _fetch_all_videos(token, max_count=20)
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
    """GET /api/analytics/heatmap/ — Best posting-time heatmap derived from real video engagement."""
    permission_classes = [IsAuthenticated]

    _HOUR_SLOTS = [
        ("12AM", range(0, 6)),
        ("6AM",  range(6, 12)),
        ("12PM", range(12, 18)),
        ("6PM",  range(18, 24)),
    ]
    _DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def get(self, request):
        token = _get_tiktok_token(request.user)
        if not token:
            return Response({"data": self._empty_heatmap(), "_debug": "no_token"})

        videos = _fetch_all_videos(token, max_count=20)
        if not videos:
            return Response({"data": self._empty_heatmap(), "_debug": "no_videos", "_debug_raw": _fetch_all_videos_debug(token)})

        # Accumulate engagement score per (hour_slot, day_of_week)
        scores = {slot: [0] * 7 for slot, _ in self._HOUR_SLOTS}
        for v in videos:
            ts = v.get("create_time")
            if not ts:
                continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            day_idx = dt.weekday()  # 0=Mon, 6=Sun
            hour = dt.hour
            engagement = v.get("like_count", 0) + v.get("comment_count", 0) + v.get("share_count", 0)
            views = v.get("view_count", 1) or 1
            score = round(engagement / views * 100, 2)
            for slot, hours in self._HOUR_SLOTS:
                if hour in hours:
                    scores[slot][day_idx] += score
                    break

        # Normalize to 0–10 scale
        all_vals = [s for row in scores.values() for s in row]
        max_val = max(all_vals) if max(all_vals) > 0 else 1

        data = []
        for slot, _ in self._HOUR_SLOTS:
            row = {"hour": slot}
            for i, day in enumerate(self._DAYS):
                row[day] = round(scores[slot][i] / max_val * 10, 1)
            data.append(row)

        return Response({"data": data, "videos_analyzed": len(videos)})

    def _empty_heatmap(self):
        return [{"hour": slot, **{d: 0 for d in self._DAYS}} for slot, _ in self._HOUR_SLOTS]


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
