"""
Platforms views — connect/disconnect social media platforms.
"""
import os
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from django.http import HttpResponse
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


class TikTokStatusView(APIView):
    """GET /api/platforms/tiktok/status/ — Check if TikTok is connected."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            platform = UserPlatform.objects.get(user=request.user, platform_name="TikTok")
            return Response({"connected": platform.connected})
        except UserPlatform.DoesNotExist:
            return Response({"connected": False})


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



# ── Facebook OAuth + Connect/Disconnect/Status ────────────────────────

FB_APP_ID       = os.getenv("FACEBOOK_APP_ID", "")
FB_APP_SECRET   = os.getenv("FACEBOOK_APP_SECRET", "")
FB_REDIRECT_URI = os.getenv("FACEBOOK_REDIRECT_URI", "")   # e.g. https://xxx.ngrok.io/api/platforms/facebook/oauth/callback/
FB_GRAPH_BASE   = "https://graph.facebook.com/v21.0"


class FacebookOAuthStartView(APIView):
    """GET /api/platforms/facebook/oauth/start/ — Return Facebook Login OAuth URL."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not FB_APP_ID or not FB_REDIRECT_URI:
            return Response(
                {"error": "Facebook app not configured on server. Set FACEBOOK_APP_ID and FACEBOOK_REDIRECT_URI."},
                status=500,
            )
        params = {
            "client_id": FB_APP_ID,
            "redirect_uri": FB_REDIRECT_URI,
            "scope": "pages_show_list,pages_read_engagement,read_insights",
            "state": str(request.user.pk),
            "response_type": "code",
        }
        auth_url = f"https://www.facebook.com/dialog/oauth?{urlencode(params)}"
        return Response({"auth_url": auth_url})


class FacebookOAuthCallbackView(APIView):
    """GET /api/platforms/facebook/oauth/callback/ — Handle Facebook redirect after Login."""
    permission_classes = []  # Called by Facebook browser redirect — no JWT

    def get(self, request):
        error = request.query_params.get("error")
        code  = request.query_params.get("code")
        state = request.query_params.get("state")

        def _html(title, body, color="#ff4444"):
            return HttpResponse(
                f"""<html><body style="font-family:sans-serif;text-align:center;
                padding-top:80px;background:#0f111e;color:white;">
                <h2 style="color:{color};">{title}</h2><p>{body}</p>
                <script>setTimeout(()=>window.close(),3000);</script>
                </body></html>""",
                content_type="text/html",
            )

        if error:
            return _html("Authorization Cancelled", f"Facebook said: {error}")
        if not code or not state:
            return _html("Invalid Callback", "Missing code or state parameter.")

        # Resolve user from state (user pk)
        User = get_user_model()
        try:
            user = User.objects.get(pk=int(state))
        except (User.DoesNotExist, ValueError):
            return _html("Invalid State", "Could not identify user.")

        # Exchange code → short-lived user token
        try:
            r = httpx.get(f"{FB_GRAPH_BASE}/oauth/access_token", params={
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "redirect_uri": FB_REDIRECT_URI,
                "code": code,
            }, timeout=10)
            user_token = r.json().get("access_token")
            if not user_token:
                raise ValueError(r.text)
        except Exception as e:
            return _html("Token Exchange Failed", str(e))

        # Exchange short-lived → long-lived user token
        try:
            r2 = httpx.get(f"{FB_GRAPH_BASE}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "fb_exchange_token": user_token,
            }, timeout=10)
            long_token = r2.json().get("access_token", user_token)
        except Exception:
            long_token = user_token

        # Get user's pages and use the first page's access token
        page_token = long_token
        try:
            r3 = httpx.get(f"{FB_GRAPH_BASE}/me/accounts", params={
                "access_token": long_token,
                "fields": "id,name,access_token",
            }, timeout=10)
            pages = r3.json().get("data", [])
            if pages:
                page_token = pages[0]["access_token"]
        except Exception:
            pass

        # Save token
        platform, _ = UserPlatform.objects.get_or_create(user=user, platform_name="Facebook")
        platform.access_token = page_token
        platform.connected    = True
        platform.connected_at = timezone.now()
        platform.save()

        return _html(
            "Facebook Connected!",
            "You can close this tab and return to the app.",
            color="#1877F2",
        )


class FacebookConnectView(APIView):
    """POST /api/platforms/facebook/connect/ — kept for internal/manual use only."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Only allow if an explicit token is provided (not empty env var shortcut)
        token = request.data.get("access_token", "").strip()
        if not token:
            return Response(
                {"error": "Use GET /api/platforms/facebook/oauth/start/ to connect via Facebook Login."},
                status=400,
            )
        platform, _ = UserPlatform.objects.get_or_create(user=request.user, platform_name="Facebook")
        platform.access_token = token
        platform.connected    = True
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
