from django.urls import path
from .views import (
    TrendListView, TrendDetailView, SaveTrendView, SavedTrendListView,
    FacebookReelListView, ScrapeTriggerView, SyncReelsToTrendsView
)

urlpatterns = [
    path("", TrendListView.as_view(), name="trend-list"),
    path("saved/", SavedTrendListView.as_view(), name="saved-trends"),
    path("reels/", FacebookReelListView.as_view(), name="facebook-reels"),
    path("scrape/", ScrapeTriggerView.as_view(), name="trend-scrape"),
    path("sync/", SyncReelsToTrendsView.as_view(), name="trends-sync"),
    path("<int:pk>/", TrendDetailView.as_view(), name="trend-detail"),
    path("<int:pk>/save/", SaveTrendView.as_view(), name="trend-save"),
]
