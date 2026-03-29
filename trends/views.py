"""
Trends views: list/filter/sort, detail, save/unsave, saved list.
Supports filtering by platform (?platform=TikTok) and sorting (?sort=growth|score|recent).
"""
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.management import call_command

from .models import Trend, SavedTrend, FacebookReel
from .serializers import TrendSerializer, SavedTrendSerializer, FacebookReelSerializer


class TrendListView(generics.ListAPIView):
    """GET /api/trends/ — List trends with optional platform filter and sort."""
    serializer_class = TrendSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
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


class FacebookReelListView(generics.ListAPIView):
    """GET /api/trends/reels/ — List scraped Facebook Reels (filtering by user's categories if provided)."""
    serializer_class = FacebookReelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = FacebookReel.objects.all()
        # Optional ?niche= query param to filter by niche
        niche = self.request.query_params.get("niche")
        if niche:
            qs = qs.filter(niche__icontains=niche)
        return qs.order_by("-play_count")


import requests

class ScrapeTriggerView(APIView):
    """POST /api/trends/scrape/ — Triggers the n8n Apify Scraping webhook."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        niche = request.data.get("niche")
        if not niche and user.categories:
            niche = user.categories[0]
        if not niche:
            niche = "tech" # fallback default
            
        webhook_url = "http://localhost:5678/webhook/scrape"
        payload = {
            "niche": niche,
            "pages": request.data.get("pages", [{"url": "https://www.facebook.com/TunisieNumerique"}])
        }
        
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code == 200:
                return Response({"message": "Scraping job triggered successfully.", "niche": niche}, status=status.HTTP_200_OK)
            elif resp.status_code == 404:
                return Response({"error": "n8n workflow is INACTIVE. Please toggle it to 'Active' in the top-right corner of the n8n editor."}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                error_hint = resp.json().get("hint", "")
            except:
                error_hint = resp.text
            return Response({"error": f"n8n logic failed ({resp.status_code}): {error_hint}"}, status=status.HTTP_400_BAD_REQUEST)
        except requests.RequestException as e:
            return Response({"error": f"Failed to reach n8n workflow: {str(e)}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class SyncReelsToTrendsView(APIView):
    """POST /api/trends/sync/ — Syncs scraped Facebook reels into the Trends table."""
    permission_classes = [AllowAny]  # Allow internal services (n8n) to trigger this without auth

    def post(self, request):
        niche = request.data.get('niche')
        try:
            if niche:
                call_command('sync_reels_to_trends', niche=niche)
            else:
                call_command('sync_reels_to_trends')
            return Response({"message": "Successfully synced Facebook reels to Trends table."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Failed to sync reels to trends: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
