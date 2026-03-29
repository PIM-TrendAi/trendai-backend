from django.urls import path
from .views import AnalyticsSummaryView, EngagementView, PlatformPerformanceView, HeatmapView, SavedTrendAnalyticsView
from .youtube_views import (
    YouTubeConnectView, YouTubeCallbackView, YouTubeStatusView,
    YouTubeDisconnectView, YouTubeChannelStatsView, YouTubeMyVideosView,
)

urlpatterns = [
    path("summary/", AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("engagement/", EngagementView.as_view(), name="analytics-engagement"),
    path("platforms/", PlatformPerformanceView.as_view(), name="analytics-platforms"),
    path("heatmap/", HeatmapView.as_view(), name="analytics-heatmap"),
    path("saved-trends/", SavedTrendAnalyticsView.as_view(), name="analytics-saved"),
    # YouTube real data
    path("youtube/connect/", YouTubeConnectView.as_view(), name="youtube-connect"),
    path("youtube/callback/", YouTubeCallbackView.as_view(), name="youtube-callback"),
    path("youtube/status/", YouTubeStatusView.as_view(), name="youtube-status"),
    path("youtube/disconnect/", YouTubeDisconnectView.as_view(), name="youtube-disconnect"),
    path("youtube/channel-stats/", YouTubeChannelStatsView.as_view(), name="youtube-channel-stats"),
    path("youtube/my-videos/", YouTubeMyVideosView.as_view(), name="youtube-my-videos"),
]
