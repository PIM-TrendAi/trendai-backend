"""
Platforms views — connect/disconnect social media platforms.
"""
from datetime import timedelta

import httpx
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import UserPlatform


class UserPlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPlatform
        fields = ["id", "platform_name", "connected", "connected_at"]
        read_only_fields = ["id", "connected_at"]


class PlatformListView(generics.ListAPIView):
    """GET /api/platforms/ — List all 5 platforms with connection status."""
    serializer_class = UserPlatformSerializer
    permission_classes = [IsAuthenticated]

    PLATFORMS = ["TikTok", "Instagram", "YouTube", "Facebook", "X"]

    def get_queryset(self):
        # Ensure all platforms exist as rows for this user
        for platform in self.PLATFORMS:
            UserPlatform.objects.get_or_create(user=self.request.user, platform_name=platform)
        return UserPlatform.objects.filter(user=self.request.user)


class PlatformUpdateView(APIView):
    """PATCH /api/platforms/{id}/ — Toggle platform connection."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            platform = UserPlatform.objects.get(pk=pk, user=request.user)
        except UserPlatform.DoesNotExist:
            return Response({"error": "Platform not found."}, status=status.HTTP_404_NOT_FOUND)

        platform.connected = not platform.connected
        platform.connected_at = timezone.now() if platform.connected else None
        platform.save()
        return Response(UserPlatformSerializer(platform).data)


class TikTokInternalTokenView(APIView):
    """
    POST /api/platforms/tiktok/internal-token/
    Called by N8n after OAuth exchange. Secured by X-Internal-Secret header.
    Body: { "creator_id": int, "access_token": str, "expires_in": int (seconds) }
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        secret = request.headers.get("X-Internal-Secret", "")
        if secret != settings.INTERNAL_API_SECRET:
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

        creator_id = request.data.get("creator_id")
        access_token = request.data.get("access_token")
        expires_in = request.data.get("expires_in", 86400)

        if not creator_id or not access_token:
            return Response({"error": "creator_id and access_token are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            creator_id = int(creator_id)
        except (TypeError, ValueError):
            return Response({"error": "creator_id must be a numeric user ID"}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        try:
            user = User.objects.get(pk=creator_id)
        except User.DoesNotExist:
            return Response({"error": "user not found"}, status=status.HTTP_404_NOT_FOUND)

        platform, _ = UserPlatform.objects.get_or_create(user=user, platform_name="TikTok")
        platform.access_token = access_token
        platform.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
        platform.connected = True
        platform.connected_at = timezone.now()
        platform.save()

        return Response({"status": "ok"})


class TikTokDebugView(APIView):
    """GET /api/platforms/tiktok/debug/ — Raw TikTok API responses for debugging."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="TikTok")
        except UserPlatform.DoesNotExist:
            return Response({"error": "TikTok not connected"}, status=404)

        token = platform.access_token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        results = {}

        # Test user info
        try:
            r = httpx.get(
                "https://open.tiktokapis.com/v2/user/info/",
                headers=headers,
                params={"fields": "follower_count,video_count,likes_count"},
                timeout=10,
            )
            results["user_info"] = {"status": r.status_code, "body": r.json()}
        except Exception as e:
            results["user_info"] = {"error": str(e)}

        # Test video list + extract IDs
        video_ids = []
        try:
            r = httpx.post(
                "https://open.tiktokapis.com/v2/video/list/",
                headers=headers,
                params={"fields": "id,title,cover_image_url"},
                json={"max_count": 5},
                timeout=10,
            )
            list_body = r.json()
            results["video_list"] = {"status": r.status_code, "body": list_body}
            video_ids = [v["id"] for v in list_body.get("data", {}).get("videos", [])]
        except Exception as e:
            results["video_list"] = {"error": str(e)}

        # Test video query (stats)
        if video_ids:
            try:
                r2 = httpx.post(
                    "https://open.tiktokapis.com/v2/video/query/",
                    headers=headers,
                    params={"fields": "id,title,view_count,like_count,comment_count,share_count"},
                    json={"filters": {"video_ids": video_ids}},
                    timeout=10,
                )
                results["video_query"] = {"status": r2.status_code, "body": r2.json()}
            except Exception as e:
                results["video_query"] = {"error": str(e)}
        else:
            results["video_query"] = "skipped — no video IDs from list"

        results["token_preview"] = token[:20] + "..." if token else None
        results["connected"] = platform.connected
        results["token_expires_at"] = str(platform.token_expires_at)
        return Response(results)


class TikTokDisconnectView(APIView):
    """POST /api/platforms/tiktok/disconnect/ — Clear token and mark disconnected."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="TikTok")
            platform.access_token = None
            platform.token_expires_at = None
            platform.connected = False
            platform.connected_at = None
            platform.save()
        except UserPlatform.DoesNotExist:
            pass
        return Response({"status": "disconnected"})


# ── Instagram Connect/Disconnect/Status ──────────────────────────────
# Since it's a single hardcoded IG Business account, we store the token
# in UserPlatform so the analytics can query the Instagram Graph API.

import os

IG_ACCESS_TOKEN = os.getenv(
    "INSTAGRAM_ACCESS_TOKEN",
    "EAAbwZCOua5JwBRF510VdWqMyHKgArwZAco5maDRa7ZATLccZCcRMlehrtkJrjXQpAc48fDlyh82Yr2aZCW88mcyckRliDKU8Dn1b9u0G26AmPYaiDbFfe2pXdsUOuYo39zDLAJrzdMQ92a5kYFtOsDoY2AquiLTXamy5cCYpRXDXTdqTUMTt1xqw7zb1I9XtYZCKOLc1dAIKyJXg5MutZBT37CoUKrsKliD0svqyyXCvR6Vsc9863bjBxeqkRyNEPUHUcmJalzdEIZA4ZApZAfnJBA0i9Q",
)
IG_BUSINESS_ACCOUNT_ID = os.getenv("IG_BUSINESS_ACCOUNT_ID", "17841480637267691")


class InstagramConnectView(APIView):
    """POST /api/platforms/instagram/connect/ — Store the IG token and mark connected."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        platform, _ = UserPlatform.objects.get_or_create(
            user=request.user, platform_name="Instagram"
        )
        platform.access_token = IG_ACCESS_TOKEN
        platform.connected = True
        platform.connected_at = timezone.now()
        platform.save()
        return Response({"status": "connected"})


class InstagramDisconnectView(APIView):
    """POST /api/platforms/instagram/disconnect/ — Clear token and mark disconnected."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="Instagram")
            platform.access_token = None
            platform.connected = False
            platform.connected_at = None
            platform.save()
        except UserPlatform.DoesNotExist:
            pass
        return Response({"status": "disconnected"})


class InstagramStatusView(APIView):
    """GET /api/platforms/instagram/status/ — Check if Instagram is connected."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="Instagram")
            return Response({"connected": platform.connected})
        except UserPlatform.DoesNotExist:
            return Response({"connected": False})


# ── Facebook Connect/Disconnect/Status ────────────────────────────────

FB_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")


class FacebookConnectView(APIView):
    """POST /api/platforms/facebook/connect/ — Store the FB token and mark connected."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        platform, _ = UserPlatform.objects.get_or_create(
            user=request.user, platform_name="Facebook"
        )
        platform.access_token = request.data.get("access_token", FB_ACCESS_TOKEN)
        platform.connected = True
        platform.connected_at = timezone.now()
        platform.save()
        return Response({"status": "connected"})


class FacebookDisconnectView(APIView):
    """POST /api/platforms/facebook/disconnect/ — Clear token and mark disconnected."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="Facebook")
            platform.access_token = None
            platform.connected = False
            platform.connected_at = None
            platform.save()
        except UserPlatform.DoesNotExist:
            pass
        return Response({"status": "disconnected"})


class FacebookStatusView(APIView):
    """GET /api/platforms/facebook/status/ — Check if Facebook is connected."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="Facebook")
            return Response({"connected": platform.connected})
        except UserPlatform.DoesNotExist:
            return Response({"connected": False})


# ── YouTube Connect/Disconnect/Status ─────────────────────────────────


class YouTubeConnectView(APIView):
    """POST /api/platforms/youtube/connect/ — Store the YT token and mark connected."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        platform, _ = UserPlatform.objects.get_or_create(
            user=request.user, platform_name="YouTube"
        )
        platform.access_token = request.data.get("access_token", "")
        platform.connected = True
        platform.connected_at = timezone.now()
        platform.save()
        return Response({"status": "connected"})


class YouTubeDisconnectView(APIView):
    """POST /api/platforms/youtube/disconnect/ — Clear token and mark disconnected."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="YouTube")
            platform.access_token = None
            platform.connected = False
            platform.connected_at = None
            platform.save()
        except UserPlatform.DoesNotExist:
            pass
        return Response({"status": "disconnected"})


class YouTubeStatusView(APIView):
    """GET /api/platforms/youtube/status/ — Check if YouTube is connected."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="YouTube")
            return Response({"connected": platform.connected})
        except UserPlatform.DoesNotExist:
            return Response({"connected": False})
