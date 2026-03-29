"""
Trends views: list/filter/sort, detail, save/unsave, saved list.
Supports filtering by platform (?platform=TikTok) and sorting (?sort=growth|score|recent).
"""
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import Trend, SavedTrend
from .serializers import TrendSerializer, SavedTrendSerializer
from .services import sync_scraped_youtube_to_trends


class TrendListView(generics.ListAPIView):
    """GET /api/trends/ — List trends with optional platform filter and sort."""
    serializer_class = TrendSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        sync_scraped_youtube_to_trends(limit=120)

        qs = Trend.objects.all()
        platform = self.request.query_params.get("platform")
        sort = self.request.query_params.get("sort", "growth")

        if platform:
            qs = qs.filter(platform=platform)

        if sort == "growth":
            qs = qs.order_by("-growth")
        elif sort == "score":
            qs = qs.order_by("-score")
        elif sort == "recent":
            qs = qs.order_by("-created_at")

        return qs


class TrendDetailView(generics.RetrieveAPIView):
    """GET /api/trends/{id}/ — Trend detail with full analytics."""
    serializer_class = TrendSerializer
    permission_classes = [IsAuthenticated]
    queryset = Trend.objects.all()


class SaveTrendView(APIView):
    """POST/DELETE /api/trends/{id}/save/ — Toggle bookmark on a trend."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        trend = Trend.objects.get(pk=pk)
        saved, created = SavedTrend.objects.get_or_create(user=request.user, trend=trend)
        if created:
            return Response({"message": "Trend saved.", "saved": True}, status=status.HTTP_201_CREATED)
        return Response({"message": "Already saved.", "saved": True}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        trend = Trend.objects.get(pk=pk)
        deleted, _ = SavedTrend.objects.filter(user=request.user, trend=trend).delete()
        if deleted:
            return Response({"message": "Trend unsaved.", "saved": False})
        return Response({"error": "Not in your saved list."}, status=status.HTTP_404_NOT_FOUND)


class SavedTrendListView(generics.ListAPIView):
    """GET /api/trends/saved/ — List the authenticated user's saved trends."""
    serializer_class = SavedTrendSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedTrend.objects.filter(user=self.request.user).select_related("trend")
