"""
Analytics app — views that aggregate user performance data.
Fetches real Facebook video stats via the Meta Graph API.
Falls back to local DB if the API is unavailable.
"""
import os
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from trends.models import SavedTrend
from ai_scripts.models import GeneratedVideo

logger = logging.getLogger(__name__)

FB_GRAPH = "https://graph.facebook.com/v22.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fb_request(url: str, timeout: int = 15) -> dict:
    """Make a GET request to the Facebook Graph API and return parsed JSON."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    data = json.loads(raw)
    if "error" in data:
        raise Exception(f"FB API error: {data['error'].get('message', data['error'])}")
    return data


# ---------------------------------------------------------------------------
# Analytics overview views (static / DB-backed)
# ---------------------------------------------------------------------------

class AnalyticsSummaryView(APIView):
    """GET /api/analytics/summary/ — Overview stats cards."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "total_views": {"value": 24500, "label": "24.5K", "trend": "+15.3%", "direction": "up"},
            "engagement": {"value": 87, "label": "87%", "trend": "+8.7%", "direction": "up"},
            "followers": {"value": 12800, "label": "12.8K", "trend": "+23.1%", "direction": "up"},
            "viral_score": {"value": 94, "label": "94", "trend": "+12.0%", "direction": "up"},
        })


class EngagementView(APIView):
    """GET /api/analytics/engagement/ — 7-day engagement line chart data."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "data": [
                {"day": "Mon", "engagement": 45, "views": 1200},
                {"day": "Tue", "engagement": 52, "views": 1450},
                {"day": "Wed", "engagement": 61, "views": 1680},
                {"day": "Thu", "engagement": 73, "views": 2100},
                {"day": "Fri", "engagement": 85, "views": 2850},
                {"day": "Sat", "engagement": 91, "views": 3200},
                {"day": "Sun", "engagement": 87, "views": 3100},
            ]
        })


class PlatformPerformanceView(APIView):
    """GET /api/analytics/platforms/ — Bar chart data by platform."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "data": [
                {"name": "TikTok", "value": 4200},
                {"name": "Instagram", "value": 3100},
                {"name": "YouTube", "value": 2800},
                {"name": "Facebook", "value": 1900},
            ]
        })


class HeatmapView(APIView):
    """GET /api/analytics/heatmap/ — Best posting-time heatmap (hour × day)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "data": [
                {"hour": "6AM",  "Mon": 2, "Tue": 3, "Wed": 4, "Thu": 5, "Fri": 8, "Sat": 9, "Sun": 7},
                {"hour": "12PM", "Mon": 5, "Tue": 6, "Wed": 7, "Thu": 8, "Fri": 9, "Sat": 8, "Sun": 6},
                {"hour": "6PM",  "Mon": 8, "Tue": 9, "Wed": 9, "Thu": 9, "Fri": 10, "Sat": 9, "Sun": 8},
                {"hour": "12AM", "Mon": 3, "Tue": 4, "Wed": 5, "Thu": 6, "Fri": 7, "Sat": 8, "Sun": 7},
            ]
        })


class SavedTrendAnalyticsView(APIView):
    """GET /api/analytics/saved-trends/ — Saved trends with scores for analytics page."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        saved = SavedTrend.objects.filter(user=request.user).select_related("trend")[:10]
        return Response({
            "data": [
                {"name": st.trend.hashtag, "score": st.trend.score}
                for st in saved
            ]
        })


# ---------------------------------------------------------------------------
# Facebook Debug View — tests token & page access
# ---------------------------------------------------------------------------

class FacebookDebugView(APIView):
    """
    GET /api/analytics/facebook-debug/
    Tests whether the configured FB token and page ID work with the Graph API.
    Returns diagnostic info for each step.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page_id = os.getenv("FB_PAGE_ID", "").strip()
        access_token = os.getenv("FB_ACCESS_TOKEN", "").strip()

        result = {
            "page_id": page_id,
            "token_present": bool(access_token),
            "token_prefix": (access_token[:25] + "...") if access_token else None,
            "tests": {},
        }

        if not page_id or not access_token:
            result["error"] = "FB_PAGE_ID or FB_ACCESS_TOKEN not configured in .env"
            return Response(result, status=400)

        # Test 1: Token validity — /me
        try:
            url = f"{FB_GRAPH}/me?fields=id,name&access_token={access_token}"
            me_data = _fb_request(url, timeout=10)
            result["tests"]["token_validity"] = {"ok": True, "data": me_data}
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:400]
            result["tests"]["token_validity"] = {"ok": False, "http_code": e.code, "body": body}
        except Exception as e:
            result["tests"]["token_validity"] = {"ok": False, "error": str(e)}

        # Test 2: Page info
        try:
            url = f"{FB_GRAPH}/{page_id}?fields=id,name,fan_count&access_token={access_token}"
            page_data = _fb_request(url, timeout=10)
            result["tests"]["page_info"] = {"ok": True, "data": page_data}
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:400]
            result["tests"]["page_info"] = {"ok": False, "http_code": e.code, "body": body}
        except Exception as e:
            result["tests"]["page_info"] = {"ok": False, "error": str(e)}

        # Test 3: Page videos endpoint
        try:
            url = (
                f"{FB_GRAPH}/{page_id}/videos"
                f"?fields=id,title,description,created_time"
                f"&limit=3&access_token={access_token}"
            )
            videos_data = _fb_request(url, timeout=10)
            result["tests"]["videos_endpoint"] = {
                "ok": True,
                "count": len(videos_data.get("data", [])),
                "sample": videos_data.get("data", [])[:2],
            }
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:400]
            result["tests"]["videos_endpoint"] = {"ok": False, "http_code": e.code, "body": body}
        except Exception as e:
            result["tests"]["videos_endpoint"] = {"ok": False, "error": str(e)}

        # Test 4: Page reels endpoint
        try:
            url = (
                f"{FB_GRAPH}/{page_id}/reels"
                f"?fields=id,description,created_time"
                f"&limit=3&access_token={access_token}"
            )
            reels_data = _fb_request(url, timeout=10)
            result["tests"]["reels_endpoint"] = {
                "ok": True,
                "count": len(reels_data.get("data", [])),
                "sample": reels_data.get("data", [])[:2],
            }
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:400]
            result["tests"]["reels_endpoint"] = {"ok": False, "http_code": e.code, "body": body}
        except Exception as e:
            result["tests"]["reels_endpoint"] = {"ok": False, "error": str(e)}

        # Test 5: insights on first found video (if any)
        first_vid = None
        for key in ("videos_endpoint", "reels_endpoint"):
            sample = result["tests"].get(key, {}).get("sample", [])
            if sample:
                first_vid = sample[0].get("id")
                break

        if first_vid:
            try:
                metrics = "total_video_views,total_video_comment_count,total_video_share_count"
                url = (
                    f"{FB_GRAPH}/{first_vid}/video_insights"
                    f"?metric={urllib.parse.quote(metrics)}"
                    f"&access_token={access_token}"
                )
                ins_data = _fb_request(url, timeout=10)
                result["tests"]["video_insights"] = {
                    "ok": True,
                    "video_id": first_vid,
                    "data": ins_data.get("data", []),
                }
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:400]
                result["tests"]["video_insights"] = {"ok": False, "video_id": first_vid, "http_code": e.code, "body": body}
            except Exception as e:
                result["tests"]["video_insights"] = {"ok": False, "video_id": first_vid, "error": str(e)}
        else:
            result["tests"]["video_insights"] = {"ok": False, "error": "No videos/reels found to test insights on"}

        return Response(result)


# ---------------------------------------------------------------------------
# Facebook Videos View — real data with graceful fallback
# ---------------------------------------------------------------------------

class FacebookVideosView(APIView):
    """
    GET /api/analytics/facebook-videos/
    Fetches real-time video statistics from the Meta Graph API.
    Each endpoint (reels, videos) is tried independently.
    video_insights are optional — if they fail, stats default to 0.
    Falls back to local DB only if NO videos were fetched from any endpoint.
    """
    permission_classes = [IsAuthenticated]

    VIDEO_INSIGHT_METRICS = [
        "total_video_views",
        "total_video_impressions",
        "total_video_reactions_by_type_total",
        "total_video_comment_count",
        "total_video_share_count",
        "total_video_avg_time_watched",
    ]

    def _fetch_insights(self, video_id: str, token: str) -> dict:
        """Fetch video-level insights. Returns empty dict on any failure (non-blocking)."""
        metrics = ",".join(self.VIDEO_INSIGHT_METRICS)
        try:
            url = (
                f"{FB_GRAPH}/{video_id}/video_insights"
                f"?metric={urllib.parse.quote(metrics)}"
                f"&access_token={token}"
            )
            data = _fb_request(url, timeout=10)
            result = {}
            for item in data.get("data", []):
                result[item["name"]] = item.get("values", [{}])[-1].get("value", 0)
            return result
        except Exception as exc:
            logger.debug("video_insights failed for %s: %s", video_id, exc)
            return {}

    def _fetch_page_videos(self, page_id: str, token: str, endpoint: str) -> list:
        """
        Fetch videos from the page, including likes and comments directly.
        Note: 'shares' field is NOT supported on video objects via the Page API.
              'video_insights' requires read_insights permission — fetched separately.
        """
        # likes.summary, comments.summary & views work directly on video objects
        fields = "id,description,title,created_time,picture,views,likes.summary(true),comments.summary(true)"
        url = (
            f"{FB_GRAPH}/{page_id}/{endpoint}"
            f"?fields={urllib.parse.quote(fields)}"
            f"&limit=25"
            f"&access_token={token}"
        )
        logger.info("Fetching FB /%s for page %s", endpoint, page_id)
        data = _fb_request(url, timeout=20)
        items = data.get("data", [])
        logger.info("FB /%s returned %d items", endpoint, len(items))
        return items

    @staticmethod
    def _build_video_entry(v: dict, insights: dict, page_id: str) -> dict:
        """
        Construct a video dict from raw API data + (optional) insights.
        - Views, Likes and Comments are read directly from v (available without special permissions).
        """
        vid_id = v.get("id", "")

        # ── Views — from direct field (no special permission needed)
        views = int(v.get("views", 0) or 0)
        # Fallback to insights if missing
        if views == 0 and insights:
            views = int(insights.get("total_video_views", 0) or insights.get("total_video_impressions", 0) or 0)

        # ── Likes — from direct field (no special permission needed)
        likes_raw = v.get("likes", {})
        if isinstance(likes_raw, dict):
            likes = int(likes_raw.get("summary", {}).get("total_count", 0) or 0)
        else:
            likes = 0
        # Also check insights reactions as a bonus
        reactions = insights.get("total_video_reactions_by_type_total", {})
        if isinstance(reactions, dict) and reactions:
            likes = max(likes, sum(int(v2) for v2 in reactions.values() if isinstance(v2, (int, float))))
        elif isinstance(reactions, (int, float)) and reactions > likes:
            likes = int(reactions)

        # ── Comments — from direct field
        comments_raw = v.get("comments", {})
        if isinstance(comments_raw, dict):
            comments_count = int(comments_raw.get("summary", {}).get("total_count", 0) or 0)
        else:
            comments_count = int(insights.get("total_video_comment_count", 0) or 0)

        # ── Shares — from insights only (direct field not available)
        shares_count = int(insights.get("total_video_share_count", 0) or 0)

        # ── Avg watch time (ms → s)
        avg_watch_ms = insights.get("total_video_avg_time_watched", 0)
        avg_watch_sec = round(float(avg_watch_ms) / 1000, 1) if avg_watch_ms else 0.0

        # ── Description / hashtags
        desc = v.get("description", "") or v.get("title", "") or "Video"
        hashtags = " ".join(w for w in desc.split() if w.startswith("#"))
        if not hashtags:
            hashtags = (desc[:55] + "…") if len(desc) > 55 else desc or "#TrendAI"

        # ── Thumbnail
        thumbnail_url = v.get("picture", "")
        thumbs = (v.get("thumbnails") or {}).get("data", [])
        if thumbs:
            thumbnail_url = thumbs[0].get("uri", thumbnail_url)

        # ── Date
        created_time = v.get("created_time", "")
        date_str = ""
        if created_time:
            try:
                dt = datetime.strptime(created_time[:19], "%Y-%m-%dT%H:%M:%S")
                date_str = dt.strftime("%d/%m/%Y")
            except ValueError:
                date_str = created_time[:10]

        return {
            "id": vid_id,
            "hashtags": hashtags,
            "views": views,
            "likes": likes,
            "comments": comments_count,
            "shares": shares_count,
            "avg_watch": avg_watch_sec,
            "status": "published",
            "script_text": desc,
            "video_url": f"https://www.facebook.com/{page_id}/videos/{vid_id}/",
            "thumbnail_url": thumbnail_url,
            "created_at": date_str,
            "session": vid_id,
            "source": "facebook_api",
        }

    def get(self, request):
        page_id = os.getenv("FB_PAGE_ID", "").strip()
        access_token = os.getenv("FB_ACCESS_TOKEN", "").strip()
        endpoint_errors = []

        if page_id and access_token:
            raw_videos = []
            seen_ids = set()

            # ── Try /videos first (main endpoint for pages)
            # Note: /reels endpoint returns HTTP 2500 "Unknown path" for most page tokens.
            # If it works in the future it will add new items without duplicating.
            for endpoint in ("videos", "reels"):
                try:
                    items = self._fetch_page_videos(page_id, access_token, endpoint)
                    added = 0
                    for item in items:
                        vid_id = item.get("id")
                        if vid_id and vid_id not in seen_ids:
                            seen_ids.add(vid_id)
                            item["_endpoint"] = endpoint
                            raw_videos.append(item)
                            added += 1
                    logger.info("FB /%s: added %d new unique items", endpoint, added)
                except urllib.error.HTTPError as e:
                    try:
                        err_body = e.read().decode()[:400]
                    except Exception:
                        err_body = "(no body)"
                    msg = f"/{endpoint}: HTTP {e.code} — {err_body}"
                    logger.warning("FB endpoint error: %s", msg)
                    endpoint_errors.append(msg)
                except Exception as e:
                    msg = f"/{endpoint}: {e}"
                    logger.warning("FB endpoint error: %s", msg)
                    endpoint_errors.append(msg)

            if raw_videos:
                # ── Build response from real FB data
                data = []
                total_views = 0
                total_engagement = 0

                for v in raw_videos:
                    vid_id = v.get("id")
                    insights = self._fetch_insights(vid_id, access_token)
                    entry = self._build_video_entry(v, insights, page_id)
                    total_views += entry["views"]
                    total_engagement += entry["likes"] + entry["comments"] + entry["shares"]
                    data.append(entry)

                data.sort(key=lambda x: x["views"], reverse=True)
                engagement_rate = (
                    round(total_engagement / total_views * 100, 1)
                    if total_views > 0 else 0.0
                )

                resp = {
                    "videos": data,
                    "summary": {
                        "total_views": total_views,
                        "total_videos": len(data),
                        "engagement": engagement_rate,
                    },
                    "source": "facebook_api",
                }
                if endpoint_errors:
                    resp["partial_errors"] = endpoint_errors
                return Response(resp)

            # No videos fetched — fall through with collected errors
            logger.warning(
                "FB API returned 0 videos from all endpoints. Errors: %s",
                endpoint_errors,
            )
        else:
            endpoint_errors.append("FB_PAGE_ID or FB_ACCESS_TOKEN not set in .env")
            logger.warning("FB credentials missing — using local DB fallback")

        # ── Fallback: local DB (mock stats from stored generated videos)
        videos = GeneratedVideo.objects.all().order_by("-created_at")[:20]
        data = []
        total_views = 0
        total_engagement = 0

        for v in videos:
            seed = v.id or 1
            views = 100 + (seed * 37 % 300)
            likes = seed * 13 % 30
            comments = seed * 7 % 10
            shares = seed * 3 % 8
            avg_watch = round(seed * 1.7 % 60, 1)
            total_views += views
            total_engagement += likes + comments + shares

            niche = v.niche or "general"
            hashtags = f"#{niche} #viral #trending"
            date_str = v.created_at.strftime("%d/%m/%Y") if v.created_at else ""

            data.append({
                "id": v.id,
                "hashtags": hashtags,
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "avg_watch": avg_watch,
                "status": v.status,
                "script_text": v.script_text or v.script or "",
                "video_url": v.video_url or "",
                "thumbnail_url": "",
                "created_at": date_str,
                "session": str(v.id),
                "source": "local_db",
            })

        engagement_rate = round(total_engagement / max(total_views, 1) * 100, 1)

        return Response({
            "videos": data,
            "summary": {
                "total_views": total_views,
                "total_videos": len(data),
                "engagement": engagement_rate,
            },
            "source": "local_db",
            "fb_errors": endpoint_errors,
            "fb_hint": (
                "FB API failed. Visit /api/analytics/facebook-debug/ to diagnose. "
                "Most likely causes: expired token, missing page permissions, or wrong page ID."
            ),
        })
