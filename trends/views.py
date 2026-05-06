"""
Trends views: list/filter/sort, detail, save/unsave, saved list.
Supports filtering by platform (?platform=TikTok) and sorting (?sort=growth|score|recent).
"""
import os
import requests
from django.db import ProgrammingError, OperationalError
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import Trend, SavedTrend, FacebookReel, YouTubeVideo, ThreadsPost
from .serializers import TrendSerializer, SavedTrendSerializer, FacebookReelSerializer, YouTubeVideoSerializer, ThreadsPostSerializer


class TrendListView(generics.ListAPIView):
    """GET /api/trends/ — List trends with optional platform filter and sort."""
    serializer_class = TrendSerializer
    permission_classes = [IsAuthenticated]

    NICHE_KEYWORDS = {
        'entertainment': ['entertainment', 'funny', 'comedy', 'viral', 'fun', 'meme', 'prank', 'challenge', 'skit'],
        'education': ['education', 'learn', 'tutorial', 'howto', 'tips', 'facts', 'science', 'history', 'study'],
        'business': ['business', 'entrepreneur', 'startup', 'marketing', 'sales', 'ceo', 'hustle', 'success'],
        'finance': ['finance', 'money', 'investing', 'stocks', 'crypto', 'budget', 'wealth', 'financial', 'income'],
        'fitness': ['fitness', 'workout', 'gym', 'health', 'exercise', 'diet', 'nutrition', 'training', 'muscle'],
        'motivation': ['motivation', 'mindset', 'inspire', 'success', 'goals', 'growth', 'positivity', 'mindfulness'],
        'gaming': ['gaming', 'gamer', 'game', 'gameplay', 'esports', 'twitch', 'ps5', 'xbox', 'minecraft', 'fortnite'],
        'art': ['art', 'design', 'drawing', 'painting', 'creative', 'artist', 'illustration', 'sketch', 'digital'],
        'fashion': ['fashion', 'style', 'outfit', 'ootd', 'clothing', 'beauty', 'makeup', 'skincare', 'aesthetic'],
        'cooking': ['cooking', 'food', 'recipe', 'chef', 'baking', 'meal', 'kitchen', 'eat', 'delicious'],
        'travel': ['travel', 'adventure', 'explore', 'trip', 'vacation', 'wanderlust', 'destination', 'vlog'],
        'tech': ['tech', 'technology', 'coding', 'programming', 'ai', 'software', 'developer', 'gadget', 'review'],
        'podcast': ['podcast', 'interview', 'talk', 'discussion', 'story', 'storytelling', 'narration'],
        'news': ['news', 'politics', 'world', 'breaking', 'update', 'current', 'economy', 'report'],
        'storytelling': ['story', 'storytime', 'narrative', 'tale', 'vlog', 'experience', 'life', 'pov'],
    }

    def get_queryset(self):
        qs = Trend.objects.all()
        platform = self.request.query_params.get("platform")
        sort = self.request.query_params.get("sort", "growth")
        niche = self.request.query_params.get("niche")

        if platform:
            qs = qs.filter(platform=platform)

        if niche and niche != "general":
            niche_key = niche.lower().strip()
            keywords = self.NICHE_KEYWORDS.get(niche_key, [niche_key])
            if keywords:
                from django.db.models import Q
                query = Q()
                for kw in keywords:
                    query |= Q(hashtag__icontains=kw) | Q(target_audience__icontains=kw)
                filtered = qs.filter(query)
                if filtered.exists():
                    qs = filtered

        if sort == "views":
            qs = qs.order_by("-total_views")
        elif sort == "likes":
            qs = qs.order_by("-total_likes")
        elif sort == "recent":
            qs = qs.order_by("-created_at")
        elif sort == "growth":
            qs = qs.order_by("-growth")
        elif sort == "score":
            qs = qs.order_by("-score")

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
    """GET /api/trends/reels/ — List scraped Facebook Reels from the N8N-managed table."""
    serializer_class = FacebookReelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            qs = FacebookReel.objects.all()
            niche = self.request.query_params.get("niche")
            if niche:
                qs = qs.filter(niche__icontains=niche)
            return qs.order_by("-play_count")[:20]
        except (ProgrammingError, OperationalError):
            return FacebookReel.objects.none()


class FacebookScrapeTriggerView(APIView):
    """POST /api/trends/facebook-scrape/ — Trigger the N8N Facebook scraping webhook."""
    permission_classes = [IsAuthenticated]

    SCRAPE_WEBHOOK_PATH = os.getenv("N8N_FACEBOOK_SCRAPE_WEBHOOK_PATH", "facebook-scrape")

    def post(self, request):
        user = request.user
        niche = request.data.get("niche", "")
        pages = request.data.get("pages", [{"url": "https://www.facebook.com/TunisieNumerique"}])

        if not niche and user.categories:
            niche = user.categories[0] if user.categories else "tech"

        base_url = os.getenv("N8N_WEBHOOK_BASE_URL", "").rstrip("/")
        if not base_url:
            return Response({"error": "N8N_WEBHOOK_BASE_URL is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        payload = {"niche": niche or "tech", "pages": pages}
        endpoints = [
            f"{base_url}/webhook/{self.SCRAPE_WEBHOOK_PATH}",
            f"{base_url}/webhook-test/{self.SCRAPE_WEBHOOK_PATH}",
        ]

        for url in endpoints:
            try:
                resp = requests.post(url, json=payload, timeout=(5, 30))
                if resp.status_code in (200, 201):
                    return Response({"message": f"Facebook scraping triggered for niche '{niche}'.", "niche": niche})
                if resp.status_code == 404:
                    continue
                return Response({"error": f"N8N returned {resp.status_code}: {resp.text[:200]}"}, status=status.HTTP_400_BAD_REQUEST)
            except requests.exceptions.ReadTimeout:
                return Response({"message": f"Facebook scraping triggered (N8N is processing).", "niche": niche})
            except requests.exceptions.ConnectionError:
                continue
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"error": "Could not reach N8N. Make sure the workflow is active."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class YouTubeVideoListView(generics.ListAPIView):
    """GET /api/trends/youtube-videos/ — List scraped YouTube videos from the N8N-managed table."""
    serializer_class = YouTubeVideoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            qs = YouTubeVideo.objects.all()
            niche = self.request.query_params.get("niche")
            if niche and niche != "general":
                niche_key = niche.lower().strip()
                # Use NICHE_KEYWORDS from TrendListView if available, else fallback to just the niche string
                keywords = TrendListView.NICHE_KEYWORDS.get(niche_key, [niche_key])
                if keywords:
                    from django.db.models import Q
                    query = Q()
                    # It's managed False, but ORM filters still translate to ILIKE queries properly
                    for kw in keywords:
                        query |= Q(tags__icontains=kw) | Q(description__icontains=kw) | Q(titre__icontains=kw) | Q(niche__icontains=niche_key)
                    qs = qs.filter(query)
            return qs.order_by("-vues")[:20]
        except (ProgrammingError, OperationalError):
            # Table doesn't exist yet (N8N hasn't run the first scrape)
            return YouTubeVideo.objects.none()


class YouTubeScrapeTriggerView(APIView):
    """POST /api/trends/youtube-scrape/ — Trigger the N8N YouTube scraping webhook."""
    permission_classes = [IsAuthenticated]

    SCRAPE_WEBHOOK_PATH = os.getenv("N8N_YOUTUBE_SCRAPE_WEBHOOK_PATH", "youtube-scrape")

    def post(self, request):
        niche = request.data.get("niche", "")

        if not niche and hasattr(request.user, 'categories') and request.user.categories:
            niche = request.user.categories[0]

        base_url = os.getenv("N8N_WEBHOOK_BASE_URL", "").rstrip("/")
        if not base_url:
            return Response({"error": "N8N_WEBHOOK_BASE_URL is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        payload = {"niche": niche or "tech"}
        endpoints = [
            f"{base_url}/webhook/{self.SCRAPE_WEBHOOK_PATH}",
            f"{base_url}/webhook-test/{self.SCRAPE_WEBHOOK_PATH}",
        ]

        for url in endpoints:
            try:
                resp = requests.post(url, json=payload, timeout=(5, 30))
                if resp.status_code in (200, 201):
                    return Response({"message": f"YouTube scraping triggered for niche '{niche}'.", "niche": niche})
                if resp.status_code == 404:
                    continue
                return Response({"error": f"N8N returned {resp.status_code}: {resp.text[:200]}"}, status=status.HTTP_400_BAD_REQUEST)
            except requests.exceptions.ReadTimeout:
                return Response({"message": f"YouTube scraping triggered (N8N is processing).", "niche": niche})
            except requests.exceptions.ConnectionError:
                continue
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"error": "Could not reach N8N. Make sure the workflow is active."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

class ThreadsPostListView(generics.ListAPIView):
    """GET /api/trends/threads-posts/ — List scraped Threads posts from the N8N-managed table."""
    serializer_class = ThreadsPostSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            qs = ThreadsPost.objects.all()
            niche = self.request.query_params.get("niche")
            if niche:
                qs = qs.filter(niche__icontains=niche)
            return qs.order_by("-like_count")[:20]
        except (ProgrammingError, OperationalError):
            return ThreadsPost.objects.none()


class ThreadsScrapeTriggerView(APIView):
    """POST /api/trends/threads-scrape/ — Trigger the N8N Threads scraping webhook."""
    permission_classes = [IsAuthenticated]

    SCRAPE_WEBHOOK_PATH = os.getenv("N8N_THREADS_SCRAPE_WEBHOOK_PATH", "threads-scrape")

    def post(self, request):
        niche = request.data.get("niche", "")
        if not niche and hasattr(request.user, 'categories') and request.user.categories:
            niche = request.user.categories[0]

        base_url = os.getenv("N8N_WEBHOOK_BASE_URL", "").rstrip("/")
        if not base_url:
            return Response({"error": "N8N_WEBHOOK_BASE_URL is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        payload = {"niche": niche or "general"}
        endpoints = [
            f"{base_url}/webhook/{self.SCRAPE_WEBHOOK_PATH}",
            f"{base_url}/webhook-test/{self.SCRAPE_WEBHOOK_PATH}",
        ]

        for url in endpoints:
            try:
                resp = requests.post(url, json=payload, timeout=(5, 30))
                if resp.status_code in (200, 201):
                    return Response({"message": f"Threads scraping triggered for niche '{niche}'.", "niche": niche})
                if resp.status_code == 404:
                    continue
                return Response({"error": f"N8N returned {resp.status_code}: {resp.text[:200]}"}, status=status.HTTP_400_BAD_REQUEST)
            except requests.exceptions.ReadTimeout:
                return Response({"message": f"Threads scraping triggered (N8N is processing).", "niche": niche})
            except requests.exceptions.ConnectionError:
                continue
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"error": "Could not reach N8N. Make sure the workflow is active."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
