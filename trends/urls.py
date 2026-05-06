from django.urls import path
from .views import (
    TrendListView, TrendDetailView, SaveTrendView, SavedTrendListView,
    FacebookReelListView, FacebookScrapeTriggerView,
    YouTubeVideoListView, YouTubeScrapeTriggerView,
    ThreadsPostListView, ThreadsScrapeTriggerView
)

urlpatterns = [
    path("", TrendListView.as_view(), name="trend-list"),
    path("saved/", SavedTrendListView.as_view(), name="saved-trends"),
    path("<int:pk>/", TrendDetailView.as_view(), name="trend-detail"),
    path("<int:pk>/save/", SaveTrendView.as_view(), name="trend-save"),
    # Facebook Reels (populated by N8N scraping workflow)
    path("reels/", FacebookReelListView.as_view(), name="facebook-reels"),
    path("facebook-scrape/", FacebookScrapeTriggerView.as_view(), name="facebook-scrape"),
    # YouTube Videos (populated by N8N scraping workflow)
    path("youtube-videos/", YouTubeVideoListView.as_view(), name="youtube-videos"),
    path("youtube-scrape/", YouTubeScrapeTriggerView.as_view(), name="youtube-scrape"),
    # Threads Posts (populated by N8N scraping workflow)
    path("threads-posts/", ThreadsPostListView.as_view(), name="threads-posts"),
    path("threads-scrape/", ThreadsScrapeTriggerView.as_view(), name="threads-scrape"),
]
