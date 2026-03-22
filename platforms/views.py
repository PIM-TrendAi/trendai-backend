"""
Platforms views — connect/disconnect social media platforms.
"""
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
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
