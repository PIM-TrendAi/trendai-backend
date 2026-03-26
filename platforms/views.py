"""
Platforms views — connect/disconnect social media platforms.
"""
from datetime import timedelta

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
