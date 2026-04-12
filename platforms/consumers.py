"""
WebSocket consumer — streams real-time TikTok video stats to connected Flutter clients.

Flow:
  1. Client connects: ws://host/ws/tiktok-stats/?token=<JWT>
  2. Consumer validates JWT, loads TikTok access token from DB
  3. Starts asyncio polling loop (every 30 s) that calls TikTok v2 API
  4. Sends JSON frame to client on each poll
  5. On disconnect the loop is cancelled
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs

import httpx
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import UntypedToken

from .models import UserPlatform

TIKTOK_VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"
TIKTOK_VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/video/query/"
POLL_INTERVAL_SECONDS = 30
MAX_VIDEOS = 20

FB_GRAPH_BASE = "https://graph.facebook.com/v21.0"
import os
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "me")

# Close codes
CODE_UNAUTHORIZED = 4001
CODE_NO_TIKTOK_TOKEN = 4002
CODE_NO_FB_TOKEN = 4003


class TikTokStatsConsumer(AsyncWebsocketConsumer):
    """Pushes real-time TikTok engagement stats to the Flutter client."""

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        # 1. Extract JWT from query string
        query_string = self.scope["query_string"].decode()
        params = parse_qs(query_string)
        token_list = params.get("token", [])

        if not token_list:
            await self.close(code=CODE_UNAUTHORIZED)
            return

        # 2. Validate JWT and resolve user
        User = get_user_model()
        try:
            validated = UntypedToken(token_list[0])
            user_id = validated.payload.get("user_id")
            if not user_id:
                raise TokenError("Missing user_id claim")
            self.user = await sync_to_async(User.objects.get)(pk=user_id)
        except (TokenError, User.DoesNotExist):
            await self.close(code=CODE_UNAUTHORIZED)
            return

        # 3. Check that a TikTok access token is stored for this user
        self._platform = await self._get_tiktok_platform()
        if not self._platform or not self._platform.access_token:
            await self.accept()
            await self.send(json.dumps({"error": "tiktok_not_connected"}))
            await self.close(code=CODE_NO_TIKTOK_TOKEN)
            return

        # 4. Accept connection and open httpx async session
        await self.accept()
        self._http_client = httpx.AsyncClient(timeout=15.0)
        self._poll_task = asyncio.create_task(self._polling_loop())

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "_poll_task"):
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "_http_client"):
            await self._http_client.aclose()

    async def receive(self, text_data: str) -> None:
        """Honour optional {"action": "refresh"} from client for immediate poll."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get("action") == "refresh" and hasattr(self, "_poll_task"):
            payload = await self._fetch_tiktok_stats()
            if payload:
                await self.send(json.dumps(payload))

    # ------------------------------------------------------------------ #
    # Polling loop                                                         #
    # ------------------------------------------------------------------ #

    async def _polling_loop(self) -> None:
        while True:
            payload = await self._fetch_tiktok_stats()
            if payload is None:
                # Fatal error already sent — close
                break
            await self.send(json.dumps(payload))
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    # ------------------------------------------------------------------ #
    # TikTok API calls                                                     #
    # ------------------------------------------------------------------ #

    async def _fetch_tiktok_stats(self) -> Optional[dict]:
        """
        Returns the payload dict, or None if a fatal error occurred
        (error frame already sent to client).
        """
        # Refresh token from DB in case it was updated
        platform = await self._get_tiktok_platform()
        if not platform or not platform.access_token:
            await self.send(json.dumps({"error": "tiktok_not_connected"}))
            await self.close()
            return None

        access_token = platform.access_token
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Step 1: Get list of video IDs
        # NOTE: TikTok v2 API requires `fields` as a URL query param, not in the body.
        list_fields = "id,title,cover_image_url,share_url"
        try:
            resp = await self._http_client.post(
                TIKTOK_VIDEO_LIST_URL,
                params={"fields": list_fields},
                headers=headers,
                json={"max_count": MAX_VIDEOS},
            )
            if resp.status_code == 401:
                await self.send(json.dumps({"error": "tiktok_token_expired"}))
                await self.close()
                return None
            list_data = resp.json()
        except httpx.HTTPError:
            await self.send(json.dumps({"error": "tiktok_api_unavailable"}))
            return None

        # Surface any TikTok API-level errors (e.g. missing scope)
        tiktok_error = list_data.get("error", {})
        if tiktok_error.get("code", "ok") != "ok":
            error_msg = tiktok_error.get("message", "")
            if "access_token" in error_msg.lower() or "permission" in error_msg.lower() or "scope" in error_msg.lower():
                await self.send(json.dumps({"error": "tiktok_token_expired"}))
                await self.close()
                return None
            return {"videos": [], "last_updated": self._now_iso(), "tiktok_error": error_msg}

        videos_raw = list_data.get("data", {}).get("videos", [])
        if not videos_raw:
            return {"videos": [], "last_updated": self._now_iso()}

        video_ids = [v["id"] for v in videos_raw]

        # Step 2: Query stats for those videos
        # Fields must also be a URL query param for video/query/
        query_fields = "id,title,cover_image_url,view_count,like_count,comment_count,share_count"
        try:
            resp = await self._http_client.post(
                TIKTOK_VIDEO_QUERY_URL,
                params={"fields": query_fields},
                headers=headers,
                json={"filters": {"video_ids": video_ids}},
            )
            if resp.status_code == 401:
                await self.send(json.dumps({"error": "tiktok_token_expired"}))
                await self.close()
                return None
            query_data = resp.json()
        except httpx.HTTPError:
            await self.send(json.dumps({"error": "tiktok_api_unavailable"}))
            return None

        stats_items = query_data.get("data", {}).get("videos", [])
        return self._build_payload(stats_items)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @sync_to_async
    def _get_tiktok_platform(self) -> "UserPlatform | None":
        try:
            return UserPlatform.objects.get(user=self.user, platform_name="TikTok")
        except UserPlatform.DoesNotExist:
            return None

    def _build_payload(self, items: list) -> dict:
        videos = []
        for item in items:
            videos.append({
                "video_id": item.get("id", ""),
                "title": item.get("title", ""),
                "thumbnail_url": item.get("cover_image_url", ""),
                "share_url": item.get("share_url", ""),
                "views": item.get("view_count", 0),
                "likes": item.get("like_count", 0),
                "comments": item.get("comment_count", 0),
                "shares": item.get("share_count", 0),
                "avg_watch_time_seconds": 0,
            })
        return {"videos": videos, "last_updated": self._now_iso()}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=timezone.utc).isoformat()


class FacebookStatsConsumer(AsyncWebsocketConsumer):
    """Pushes real-time Facebook page post stats to the Flutter client."""

    async def connect(self) -> None:
        query_string = self.scope["query_string"].decode()
        params = parse_qs(query_string)
        token_list = params.get("token", [])

        if not token_list:
            await self.close(code=CODE_UNAUTHORIZED)
            return

        User = get_user_model()
        try:
            validated = UntypedToken(token_list[0])
            user_id = validated.payload.get("user_id")
            if not user_id:
                raise TokenError("Missing user_id claim")
            self.user = await sync_to_async(User.objects.get)(pk=user_id)
        except (TokenError, User.DoesNotExist):
            await self.close(code=CODE_UNAUTHORIZED)
            return

        self._platform = await self._get_fb_platform()
        if not self._platform or not self._platform.access_token:
            await self.accept()
            await self.send(json.dumps({"error": "facebook_not_connected"}))
            await self.close(code=CODE_NO_FB_TOKEN)
            return

        await self.accept()
        self._http_client = httpx.AsyncClient(timeout=15.0)
        self._poll_task = asyncio.create_task(self._polling_loop())

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "_poll_task"):
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "_http_client"):
            await self._http_client.aclose()

    async def receive(self, text_data: str) -> None:
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get("action") == "refresh" and hasattr(self, "_poll_task"):
            payload = await self._fetch_fb_stats()
            if payload:
                await self.send(json.dumps(payload))

    async def _polling_loop(self) -> None:
        while True:
            payload = await self._fetch_fb_stats()
            if payload is None:
                break
            await self.send(json.dumps(payload))
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _fetch_fb_stats(self) -> Optional[dict]:
        platform = await self._get_fb_platform()
        if not platform or not platform.access_token:
            await self.send(json.dumps({"error": "facebook_not_connected"}))
            await self.close()
            return None

        access_token = platform.access_token

        try:
            resp = await self._http_client.get(
                f"{FB_GRAPH_BASE}/{FB_PAGE_ID}/posts",
                params={
                    "fields": "id,message,created_time,full_picture,permalink_url,"
                              "likes.summary(true),comments.summary(true),shares",
                    "limit": 20,
                    "access_token": access_token,
                },
            )
            if resp.status_code == 401:
                await self.send(json.dumps({"error": "facebook_token_expired"}))
                await self.close()
                return None
            if resp.status_code != 200:
                return {"posts": [], "last_updated": self._now_iso()}

            posts_raw = resp.json().get("data", [])
        except httpx.HTTPError:
            await self.send(json.dumps({"error": "facebook_api_unavailable"}))
            return {"posts": [], "last_updated": self._now_iso()}

        posts = []
        for p in posts_raw:
            posts.append({
                "post_id": p.get("id", ""),
                "message": (p.get("message") or "")[:120],
                "created_time": p.get("created_time", ""),
                "thumbnail_url": p.get("full_picture", ""),
                "permalink": p.get("permalink_url", ""),
                "likes": p.get("likes", {}).get("summary", {}).get("total_count", 0),
                "comments": p.get("comments", {}).get("summary", {}).get("total_count", 0),
                "shares": p.get("shares", {}).get("count", 0),
            })

        return {"posts": posts, "last_updated": self._now_iso()}

    @sync_to_async
    def _get_fb_platform(self) -> "UserPlatform | None":
        try:
            return UserPlatform.objects.get(user=self.user, platform_name="Facebook")
        except UserPlatform.DoesNotExist:
            return None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=timezone.utc).isoformat()
