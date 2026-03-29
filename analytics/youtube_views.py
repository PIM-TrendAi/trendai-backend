"""
YouTube Analytics Views — real data from YouTube Data API v3.
Requires user to have youtube_access_token stored on their profile.
Also exposes OAuth connect/callback endpoints.
"""
import os
import requests
from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "AIzaSyB6siRvBv2gX01WMXvwSlK8GSZI-TN8hEA")
REDIRECT_URI = os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8000/api/analytics/youtube/callback/")

SCOPES = " ".join([
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
])


class YouTubeConnectView(APIView):
    """GET /api/analytics/youtube/connect/ — Returns OAuth URL for YouTube connection.
    Also accepts ?api_key=... to store a direct YouTube API key without full OAuth.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Quick connect: store API key directly (useful for demo without OAuth setup)
        api_key = request.query_params.get("api_key")
        channel_id = request.query_params.get("channel_id", "")
        if api_key:
            request.user.youtube_access_token = api_key
            request.user.youtube_channel_id = channel_id
            request.user.save(update_fields=["youtube_access_token", "youtube_channel_id"])
            return Response({"status": "connected", "method": "api_key"})

        # Full OAuth flow — if Google credentials configured
        if GOOGLE_CLIENT_ID:
            params = {
                "client_id": GOOGLE_CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": SCOPES,
                "access_type": "offline",
                "prompt": "consent",
                "state": str(request.user.id),
            }
            oauth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
            return Response({"oauth_url": oauth_url})

        return Response(
            {"error": "Google OAuth not configured. Use ?api_key=YOUR_KEY to connect directly."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class YouTubeCallbackView(APIView):
    """GET /api/analytics/youtube/callback/ — Handles OAuth callback from Google."""
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get("code")
        user_id = request.query_params.get("state")
        if not code or not user_id:
            return Response({"error": "Missing code or state"}, status=400)

        # Exchange code for tokens
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if token_response.status_code != 200:
            return Response({"error": "Token exchange failed"}, status=400)

        tokens = token_response.json()
        from accounts.models import User
        try:
            user = User.objects.get(pk=user_id)
            user.youtube_access_token = tokens.get("access_token", "")
            user.youtube_refresh_token = tokens.get("refresh_token", "")
            user.save(update_fields=["youtube_access_token", "youtube_refresh_token"])
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        return HttpResponseRedirect("trendai://youtube-connected")


class YouTubeStatusView(APIView):
    """GET /api/analytics/youtube/status/ — Check if YouTube is connected."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_connected = bool(user.youtube_access_token)
        return Response({
            "connected": is_connected,
            "channel_id": user.youtube_channel_id or None,
        })


class YouTubeDisconnectView(APIView):
    """POST /api/analytics/youtube/disconnect/ — Remove stored tokens."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.youtube_access_token = ""
        request.user.youtube_refresh_token = ""
        request.user.youtube_channel_id = ""
        request.user.save(update_fields=["youtube_access_token", "youtube_refresh_token", "youtube_channel_id"])
        return Response({"status": "disconnected"})


def _yt_get(path: str, params: dict, token: str) -> dict | None:
    """Helper: call YouTube Data API with stored token or API key.
    Detects API keys by their AIza prefix. Otherwise treats as OAuth token.
    """
    p = dict(params)  # copy to avoid mutating caller's dict
    if token.startswith("AIza"):
        # Google API key
        p["key"] = token
    else:
        # OAuth access token
        p["access_token"] = token
    try:
        r = requests.get(
            f"https://www.googleapis.com/youtube/v3{path}",
            params=p,
            timeout=10,
        )
        if r.status_code != 200:
            print(f"[YT API] {path} -> {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        print(f"[YT API] {path} exception: {e}")
        return None


class YouTubeChannelStatsView(APIView):
    """GET /api/analytics/youtube/channel-stats/ — Real channel stats."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        token = user.youtube_access_token
        if not token:
            return Response({"error": "YouTube not connected"}, status=400)

        channel_id = user.youtube_channel_id or "mine"
        params = {
            "part": "statistics,snippet",
            "id" if channel_id != "mine" else "mine": channel_id if channel_id != "mine" else "true",
        }
        if channel_id != "mine":
            params = {"part": "statistics,snippet", "id": channel_id}
        else:
            params = {"part": "statistics,snippet", "mine": "true"}

        data = _yt_get("/channels", params, token)
        if not data or not data.get("items"):
            # Use API key fallback with a public channel search
            fallback = _yt_get("/channels", {
                "part": "statistics,snippet",
                "id": channel_id,
                "key": YOUTUBE_API_KEY,
            }, YOUTUBE_API_KEY)
            if fallback and fallback.get("items"):
                data = fallback
            else:
                return Response({"error": "Could not fetch channel data"}, status=502)

        item = data["items"][0]
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})

        def _fmt(n):
            n = int(n or 0)
            if n >= 1000000:
                return f"{n/1000000:.1f}M"
            if n >= 1000:
                return f"{n/1000:.1f}K"
            return str(n)

        return Response({
            "channel_name": snippet.get("title", "My Channel"),
            "channel_thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url"),
            "subscriber_count": _fmt(stats.get("subscriberCount", 0)),
            "view_count": _fmt(stats.get("viewCount", 0)),
            "video_count": _fmt(stats.get("videoCount", 0)),
            "subscriber_count_raw": int(stats.get("subscriberCount", 0)),
            "view_count_raw": int(stats.get("viewCount", 0)),
        })


class YouTubeMyVideosView(APIView):
    """GET /api/analytics/youtube/my-videos/ — Published videos on user's channel."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        token = user.youtube_access_token
        if not token:
            return Response({"error": "YouTube not connected"}, status=400)

        channel_id = user.youtube_channel_id

        # Search for videos on the channel
        search_params = {
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "type": "video",
            "maxResults": 10,
        } if channel_id else {
            "part": "snippet",
            "forMine": "true",
            "order": "date",
            "type": "video",
            "maxResults": 10,
        }

        search_data = _yt_get("/search", search_params, token)
        if not search_data or not search_data.get("items"):
            print(f"[YT] No search results for channel {channel_id}")
            return Response({"results": []})

        video_ids = [
            item["id"]["videoId"]
            for item in search_data["items"]
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return Response({"results": []})

        # Fetch statistics for all found videos in one request
        stats_data = _yt_get("/videos", {
            "part": "statistics,snippet",
            "id": ",".join(video_ids),
        }, token)

        results = []
        for item in (stats_data or {}).get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = (
                thumbnails.get("maxres", {}).get("url") or
                thumbnails.get("high", {}).get("url") or
                thumbnails.get("medium", {}).get("url") or
                thumbnails.get("default", {}).get("url") or ""
            )
            results.append({
                "video_id": item["id"],
                "title": snippet.get("title", "Untitled"),
                "thumbnail": thumbnail,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "published_at": snippet.get("publishedAt", ""),
                "tags": snippet.get("tags", [])[:5],
                "youtube_url": f"https://youtube.com/watch?v={item['id']}",
            })

        return Response({"results": results})
