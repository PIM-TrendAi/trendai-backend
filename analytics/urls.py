from django.urls import path
from .views import (
    AnalyticsSummaryView,
    EngagementView,
    PlatformPerformanceView,
    HeatmapView,
    SavedTrendAnalyticsView,
    FacebookVideosView,
    FacebookDebugView,
)

urlpatterns = [
    path("summary/", AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("engagement/", EngagementView.as_view(), name="analytics-engagement"),
    path("platforms/", PlatformPerformanceView.as_view(), name="analytics-platforms"),
    path("heatmap/", HeatmapView.as_view(), name="analytics-heatmap"),
    path("saved-trends/", SavedTrendAnalyticsView.as_view(), name="analytics-saved"),
    path("facebook-videos/", FacebookVideosView.as_view(), name="analytics-facebook-videos"),
    path("facebook-debug/", FacebookDebugView.as_view(), name="analytics-facebook-debug"),
]
