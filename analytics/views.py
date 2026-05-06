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
        fb_token = _get_facebook_token(request.user)
        ig_token = _get_instagram_token(request.user)

        # 1. TikTok Stats
        tk_score = 0
        total_views = 0
        engagement = 0.0
        followers = 0
        if token:
            user_info = _fetch_user_info(token) or {}
            videos = _fetch_all_videos(token)
            followers = user_info.get("follower_count", 0)
            tk_likes = user_info.get("likes_count", 0)
            tk_views = sum(v.get("view_count", 0) for v in videos)
            tk_comments = sum(v.get("comment_count", 0) for v in videos)
            tk_shares = sum(v.get("share_count", 0) for v in videos)
            tk_interactions = tk_likes + tk_comments + tk_shares
            
            total_views = tk_views
            engagement = round((tk_interactions / tk_views * 100), 1) if tk_views > 0 else 0.0
            tk_score = min(100, round((engagement * 0.4) + (min(tk_views, 1_000_000) / 10_000)))

        # 2. Facebook Stats
        fb_score = 0
        if fb_token:
            fb_posts = _fetch_fb_posts(fb_token)
            f_likes = sum(p.get("likes", {}).get("summary", {}).get("total_count", 0) for p in fb_posts)
            f_views = sum(p.get("impressions", 0) for p in fb_posts)
            if f_views > 0:
                f_eng = (f_likes / f_views) * 100
                fb_score = min(100, round((f_eng * 5) + (min(f_views, 500_000) / 5_000)))

        # 3. Instagram Stats
        ig_score = 0
        if ig_token:
            ig_media = _fetch_ig_media(ig_token)
            i_likes = sum(m.get("like_count", 0) for m in ig_media)
            i_views = sum(m.get("reach", 0) for m in ig_media)
            if i_views > 0:
                i_eng = (i_likes / i_views) * 100
                ig_score = min(100, round((i_eng * 6) + (min(i_views, 500_000) / 5_000)))

        return Response({
            "total_views":  _metric(total_views,  _fmt(total_views)),
            "engagement":   _metric(engagement,   f"{engagement}%"),
            "followers":    _metric(followers,     _fmt(followers)),
            "viral_score":  _metric(tk_score,      str(tk_score)),
            "heatmap": {
                "TikTok": tk_score if token else 0,
                "Instagram": ig_score if ig_token else 0,
                "YouTube": 78, # Mock for now
                "Facebook": fb_score if fb_token else 0,
                "X": 71, # Mock for now
            }
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
    """GET /api/analytics/platforms/ — Bar chart (TikTok + Facebook real, others N/A)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = _get_tiktok_token(request.user)
        tiktok_views = 0
        if token:
            videos = _fetch_all_videos(token)
            tiktok_views = sum(v.get("view_count", 0) for v in videos)

        fb_token = _get_facebook_token(request.user)
        fb_views = 0
        if fb_token:
            fb_posts = _fetch_fb_posts(fb_token)
            fb_views = sum(p.get("impressions", 0) for p in fb_posts)

        return Response({
            "data": [
                {"name": "TikTok",    "value": tiktok_views},
                {"name": "Instagram", "value": 0},
                {"name": "YouTube",   "value": 0},
                {"name": "Facebook",  "value": fb_views},
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


# ── Instagram Stats ──────────────────────────────────────────────────

import os

IG_BUSINESS_ACCOUNT_ID = os.getenv("IG_BUSINESS_ACCOUNT_ID", "17841480637267691")
IG_GRAPH_BASE = "https://graph.facebook.com/v21.0"


def _get_instagram_token(user):
    """Return the stored Instagram access token for *user*, or .env fallback."""
    try:
        platform = UserPlatform.objects.get(user=user, platform_name="Instagram")
        if platform.connected and platform.access_token:
            return platform.access_token
    except UserPlatform.DoesNotExist:
        pass
    return os.getenv("INSTAGRAM_ACCESS_TOKEN")


def _fetch_ig_media(token, limit=20):
    """Fetch recent Instagram media with insights."""
    try:
        # Get recent media
        resp = httpx.get(
            f"{IG_GRAPH_BASE}/{IG_BUSINESS_ACCOUNT_ID}/media",
            params={
                "fields": "id,caption,media_type,timestamp,thumbnail_url,permalink,like_count,comments_count",
                "limit": limit,
                "access_token": token,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        media = resp.json().get("data", [])

        # Fetch insights for each media
        for item in media:
            try:
                metrics = "reach,plays" if item.get("media_type") == "VIDEO" else "reach,impressions"
                r = httpx.get(
                    f"{IG_GRAPH_BASE}/{item['id']}/insights",
                    params={"metric": metrics, "access_token": token},
                    timeout=10,
                )
                if r.status_code == 200:
                    for m in r.json().get("data", []):
                        item[m["name"]] = m["values"][0]["value"] if m.get("values") else 0
            except Exception:
                pass
        return media
    except httpx.HTTPError:
        return []


def _fetch_ig_profile(token):
    """Fetch Instagram profile info."""
    try:
        resp = httpx.get(
            f"{IG_GRAPH_BASE}/{IG_BUSINESS_ACCOUNT_ID}",
            params={
                "fields": "followers_count,media_count,username,profile_picture_url",
                "access_token": token,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except httpx.HTTPError:
        pass
    return None


class InstagramStatsView(APIView):
    """GET /api/analytics/instagram/ — Instagram media stats from Graph API."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = _get_instagram_token(request.user)
        if not token:
            return Response({
                "connected": False,
                "profile": None,
                "media": [],
                "summary": {"total_likes": 0, "total_comments": 0, "total_reach": 0, "total_plays": 0},
            })

        profile = _fetch_ig_profile(token)
        media = _fetch_ig_media(token)

        total_likes = sum(m.get("like_count", 0) for m in media)
        total_comments = sum(m.get("comments_count", 0) for m in media)
        total_reach = sum(m.get("reach", 0) for m in media)
        total_plays = sum(m.get("plays", 0) for m in media)

        return Response({
            "connected": True,
            "profile": profile,
            "media": [
                {
                    "id": m.get("id"),
                    "caption": (m.get("caption") or "")[:100],
                    "media_type": m.get("media_type"),
                    "timestamp": m.get("timestamp"),
                    "permalink": m.get("permalink"),
                    "thumbnail_url": m.get("thumbnail_url"),
                    "likes": m.get("like_count", 0),
                    "comments": m.get("comments_count", 0),
                    "reach": m.get("reach", 0),
                    "plays": m.get("plays", 0),
                }
                for m in media
            ],
            "summary": {
                "total_likes": total_likes,
                "total_comments": total_comments,
                "total_reach": total_reach,
                "total_plays": total_plays,
                "followers": profile.get("followers_count", 0) if profile else 0,
            },
        })


# ── Facebook Stats ────────────────────────────────────────────────────────────

FB_GRAPH_BASE = "https://graph.facebook.com/v24.0"
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "me")


def _get_facebook_token(user):
    """Return the stored Facebook access token for *user*, or None."""
    try:
        platform = UserPlatform.objects.get(user=user, platform_name="Facebook")
        if platform.connected and platform.access_token:
            return platform.access_token
    except UserPlatform.DoesNotExist:
        pass
    
    # Global fallback if specified in .env
    return os.getenv("FACEBOOK_ACCESS_TOKEN")


def _fetch_fb_page_info(token):
    """Fetch Facebook page name, fan_count, followers_count."""
    try:
        resp = httpx.get(
            f"{FB_GRAPH_BASE}/{FB_PAGE_ID}",
            params={"fields": "name,fan_count,followers_count,picture.type(large)", "access_token": token},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except httpx.HTTPError:
        pass
    return None


def _fetch_fb_posts(token, limit=20):
    """Fetch recent page posts with likes, comments, shares and impressions."""
    try:
        resp = httpx.get(
            f"{FB_GRAPH_BASE}/{FB_PAGE_ID}/posts",
            params={
                "fields": "id,message,created_time,full_picture,permalink_url,"
                          "likes.summary(true),comments.summary(true),shares",
                "limit": limit,
                "access_token": token,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        posts = resp.json().get("data", [])

        # Fetch impressions and video views per post
        for post in posts:
            post.setdefault("impressions", 0)
            post.setdefault("video_views", 0)
            try:
                # Expanded metrics for different types of video content
                metrics = "post_impressions_unique,post_video_views,post_video_views_clicked_to_play"
                r = httpx.get(
                    f"{FB_GRAPH_BASE}/{post['id']}/insights",
                    params={"metric": metrics, "access_token": token},
                    timeout=8,
                )
                if r.status_code == 200:
                    for m in r.json().get("data", []):
                        val = m.get("values", [{}])[-1].get("value", 0)
                        m_name = m.get("name")
                        if m_name == "post_impressions_unique":
                            post["impressions"] = val
                        elif m_name in ["post_video_views", "post_video_views_clicked_to_play"]:
                            # Aggregate views if multiple metrics return
                            post["video_views"] = max(post["video_views"], val)
            except Exception:
                pass

        return posts
    except httpx.HTTPError:
        return []


class FacebookStatsView(APIView):
    """GET /api/analytics/facebook/ — Facebook page stats from Graph API."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = _get_facebook_token(request.user)
        if not token:
            return Response({
                "connected": False,
                "profile": None,
                "posts": [],
                "summary": {"total_likes": 0, "total_comments": 0, "total_impressions": 0, "total_shares": 0},
            })

        profile = _fetch_fb_page_info(token)
        posts = _fetch_fb_posts(token)

        def _likes(p):
            return p.get("likes", {}).get("summary", {}).get("total_count", 0)

        def _comments(p):
            return p.get("comments", {}).get("summary", {}).get("total_count", 0)

        def _shares(p):
            return p.get("shares", {}).get("count", 0)

        total_likes = sum(_likes(p) for p in posts)
        total_comments = sum(_comments(p) for p in posts)
        total_impressions = sum(p.get("impressions", 0) for p in posts)
        total_views = sum(p.get("video_views", 0) for p in posts)
        total_shares = sum(_shares(p) for p in posts)

        # Fans (Likes) vs Followers
        fans = profile.get("fan_count", 0) if profile else 0
        followers = profile.get("followers_count", 0) if profile else 0

        return Response({
            "connected": True,
            "profile": profile,
            "posts": [
                {
                    "id": p.get("id"),
                    "message": (p.get("message") or "")[:120],
                    "created_time": p.get("created_time"),
                    "thumbnail_url": p.get("full_picture"),
                    "permalink": p.get("permalink_url"),
                    "likes": _likes(p),
                    "comments": _comments(p),
                    "shares": _shares(p),
                    "impressions": p.get("impressions", 0),
                    "views": p.get("video_views", 0),
                }
                for p in posts
            ],
            "summary": {
                "total_likes": total_likes,
                "total_comments": total_comments,
                "total_impressions": total_impressions,
                "total_views": total_views,
                "total_shares": total_shares,
                "fans": fans,
                "followers": followers,
            },
        })


# ── YouTube Stats ─────────────────────────────────────────────────────────────

YT_API_BASE = "https://www.googleapis.com/youtube/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
_YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
_YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "")


def _get_youtube_platform(user):
    """Return UserPlatform for YouTube or None."""
    try:
        p = UserPlatform.objects.get(user=user, platform_name="YouTube")
        return p if p.connected else None
    except UserPlatform.DoesNotExist:
        return None


def _refresh_youtube_token(platform):
    """Attempt to refresh the access token; returns new token or None."""
    if not platform.refresh_token:
        return None
    try:
        resp = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": _GOOGLE_CLIENT_ID,
                "client_secret": _GOOGLE_CLIENT_SECRET,
                "refresh_token": platform.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            new_token = data.get("access_token")
            expires_in = int(data.get("expires_in") or 0)
            if new_token:
                platform.access_token = new_token
                if expires_in:
                    from django.utils import timezone as dj_tz
                    platform.token_expires_at = dj_tz.now() + timedelta(seconds=expires_in)
                platform.save(update_fields=["access_token", "token_expires_at"])
                return new_token
    except Exception:
        pass
    return None


def _yt_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _fetch_yt_channel(token=None, api_key=None, channel_id=None):
    """Return channel snippet+statistics dict or None.
    Uses OAuth token (mine=true) or API key + channel_id for public data."""
    try:
        if token:
            resp = httpx.get(
                f"{YT_API_BASE}/channels",
                params={"part": "snippet,statistics", "mine": "true"},
                headers=_yt_headers(token),
                timeout=10,
            )
        elif api_key and channel_id:
            resp = httpx.get(
                f"{YT_API_BASE}/channels",
                params={"part": "snippet,statistics", "id": channel_id, "key": api_key},
                timeout=10,
            )
        else:
            return None
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                return items[0]
    except httpx.HTTPError:
        pass
    return None


def _fetch_yt_videos(token=None, max_results=20, api_key=None, channel_id=None):
    """Return list of video stat dicts using the uploads playlist.
    Uses OAuth token (mine=true) or API key + channel_id for public data."""
    try:
        # Step 1: get the uploads playlist ID
        if token:
            ch_resp = httpx.get(
                f"{YT_API_BASE}/channels",
                params={"part": "contentDetails", "mine": "true"},
                headers=_yt_headers(token),
                timeout=10,
            )
        elif api_key and channel_id:
            ch_resp = httpx.get(
                f"{YT_API_BASE}/channels",
                params={"part": "contentDetails", "id": channel_id, "key": api_key},
                timeout=10,
            )
        else:
            return []

        if ch_resp.status_code != 200:
            return []
        items = ch_resp.json().get("items", [])
        if not items:
            return []
        uploads_playlist_id = (
            items[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads", "")
        )
        if not uploads_playlist_id:
            return []

        # Step 2: list recent items from uploads playlist
        pl_params = {"part": "snippet", "playlistId": uploads_playlist_id, "maxResults": max_results}
        pl_headers = _yt_headers(token) if token else {}
        if not token and api_key:
            pl_params["key"] = api_key
        pl_resp = httpx.get(f"{YT_API_BASE}/playlistItems", params=pl_params, headers=pl_headers, timeout=10)
        if pl_resp.status_code != 200:
            return []
        video_ids = [
            i["snippet"]["resourceId"]["videoId"]
            for i in pl_resp.json().get("items", [])
            if i.get("snippet", {}).get("resourceId", {}).get("kind") == "youtube#video"
        ]
        if not video_ids:
            return []

        # Step 3: fetch statistics + snippet for those video IDs
        stats_params = {"part": "snippet,statistics", "id": ",".join(video_ids)}
        stats_headers = _yt_headers(token) if token else {}
        if not token and api_key:
            stats_params["key"] = api_key
        stats_resp = httpx.get(f"{YT_API_BASE}/videos", params=stats_params, headers=stats_headers, timeout=10)
        if stats_resp.status_code != 200:
            return []

        videos = []
        for item in stats_resp.json().get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            thumbnails = snippet.get("thumbnails", {})
            thumb = (
                thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
                or ""
            )
            videos.append({
                "video_id": item.get("id", ""),
                "title": snippet.get("title", ""),
                "thumbnail_url": thumb,
                "published_at": snippet.get("publishedAt", ""),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
            })
        return videos
    except httpx.HTTPError:
        return []


class YouTubeStatsView(APIView):
    """GET /api/analytics/youtube/ — YouTube channel + video stats."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        platform = _get_youtube_platform(request.user)
        api_key = _YOUTUBE_API_KEY
        channel_id = _YOUTUBE_CHANNEL_ID

        if not platform and not (api_key and channel_id):
            return Response({
                "connected": False,
                "channel": None,
                "videos": [],
                "summary": {"subscribers": 0, "total_views": 0, "total_likes": 0, "video_count": 0},
            })

        token = None
        if platform:
            token = platform.access_token
            # Skip fake/manual tokens
            if token in ("manual_connected", "demo", "") or not token:
                token = None
            elif platform.token_expires_at:
                from django.utils import timezone as dj_tz
                if dj_tz.now() >= platform.token_expires_at:
                    refreshed = _refresh_youtube_token(platform)
                    token = refreshed if refreshed else None

        # Try OAuth token first, fall back to API key
        channel = None
        if token:
            channel = _fetch_yt_channel(token=token)
            if channel is None and platform and platform.refresh_token:
                refreshed = _refresh_youtube_token(platform)
                if refreshed:
                    token = refreshed
                    channel = _fetch_yt_channel(token=token)

        if channel is None and api_key and channel_id:
            channel = _fetch_yt_channel(api_key=api_key, channel_id=channel_id)
            token = None  # use api_key path for videos too

        if channel is None:
            return Response({
                "connected": True,
                "error": "youtube_token_expired",
                "channel": None,
                "videos": [],
                "summary": {"subscribers": 0, "total_views": 0, "total_likes": 0, "video_count": 0},
            })

        videos = _fetch_yt_videos(
            token=token,
            api_key=api_key if not token else None,
            channel_id=channel_id if not token else None,
        )
        stats = channel.get("statistics", {})
        snippet = channel.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        channel_thumb = (
            thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
            or ""
        )

        total_likes = sum(v["likes"] for v in videos)
        total_views_videos = sum(v["views"] for v in videos)

        return Response({
            "connected": True,
            "channel": {
                "id": channel.get("id", ""),
                "title": snippet.get("title", ""),
                "thumbnail_url": channel_thumb,
                "custom_url": snippet.get("customUrl", ""),
            },
            "videos": videos,
            "summary": {
                "subscribers": int(stats.get("subscriberCount", 0)),
                "total_views": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "total_likes": total_likes,
                "recent_views": total_views_videos,
            },
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
