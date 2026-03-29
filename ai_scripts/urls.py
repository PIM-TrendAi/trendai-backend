from django.urls import path
from .views import (
    GenerateScriptView, 
    SavedScriptListView,
    YouTubeVideoListView,
    YouTubeGeneratedListView,
    ProxyGenerateVideoView,
    ProxyScrapeTrendsView
)

urlpatterns = [
    # Legacy
    path("", SavedScriptListView.as_view(), name="script-list"),
    path("generate/", GenerateScriptView.as_view(), name="script-generate"),
    
    # YouTube Integration (Phase 4)
    path("youtube/trends/", YouTubeVideoListView.as_view(), name="yt-trends"),
    path("youtube/history/", YouTubeGeneratedListView.as_view(), name="yt-history"),
    path("youtube/generate/", ProxyGenerateVideoView.as_view(), name="yt-generate"),
    path("youtube/scrape/", ProxyScrapeTrendsView.as_view(), name="yt-scrape"),
]
