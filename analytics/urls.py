from django.urls import path
from .views import (
    AnalyticsSummaryView, EngagementView, PlatformPerformanceView,
    HeatmapView, SavedTrendAnalyticsView, InstagramStatsView, FacebookStatsView,
    YouTubeStatsView,
)

urlpatterns = [
    path("summary/", AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("engagement/", EngagementView.as_view(), name="analytics-engagement"),
    path("platforms/", PlatformPerformanceView.as_view(), name="analytics-platforms"),
    path("heatmap/", HeatmapView.as_view(), name="analytics-heatmap"),
    path("saved-trends/", SavedTrendAnalyticsView.as_view(), name="analytics-saved"),
    path("instagram/", InstagramStatsView.as_view(), name="analytics-instagram"),
    path("facebook/", FacebookStatsView.as_view(), name="analytics-facebook"),
    path("youtube/", YouTubeStatsView.as_view(), name="analytics-youtube"),
]
