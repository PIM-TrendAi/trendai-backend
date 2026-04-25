from django.urls import path
from .views import (
    PlatformListView, PlatformUpdateView,
    TikTokInternalTokenView, TikTokDisconnectView, TikTokDebugView, TikTokStatusView,
    InstagramConnectView, InstagramDisconnectView, InstagramStatusView,
    FacebookOAuthStartView, FacebookOAuthCallbackView,
    FacebookConnectView, FacebookDisconnectView, FacebookStatusView,
    YouTubeConnectView, YouTubeDisconnectView, YouTubeStatusView,
    ThreadsConnectView, ThreadsDisconnectView, ThreadsStatusView,
)

urlpatterns = [
    path("", PlatformListView.as_view(), name="platform-list"),
    path("<int:pk>/", PlatformUpdateView.as_view(), name="platform-update"),
    path("tiktok/internal-token/", TikTokInternalTokenView.as_view(), name="tiktok-internal-token"),
    path("tiktok/disconnect/", TikTokDisconnectView.as_view(), name="tiktok-disconnect"),
    path("tiktok/status/", TikTokStatusView.as_view(), name="tiktok-status"),
    path("tiktok/debug/", TikTokDebugView.as_view(), name="tiktok-debug"),
    path("instagram/connect/", InstagramConnectView.as_view(), name="instagram-connect"),
    path("instagram/disconnect/", InstagramDisconnectView.as_view(), name="instagram-disconnect"),
    path("instagram/status/", InstagramStatusView.as_view(), name="instagram-status"),
    path("facebook/oauth/start/", FacebookOAuthStartView.as_view(), name="facebook-oauth-start"),
    path("facebook/oauth/callback/", FacebookOAuthCallbackView.as_view(), name="facebook-oauth-callback"),
    path("facebook/connect/", FacebookConnectView.as_view(), name="facebook-connect"),
    path("facebook/disconnect/", FacebookDisconnectView.as_view(), name="facebook-disconnect"),
    path("facebook/status/", FacebookStatusView.as_view(), name="facebook-status"),
    path("youtube/connect/", YouTubeConnectView.as_view(), name="youtube-connect"),
    path("youtube/disconnect/", YouTubeDisconnectView.as_view(), name="youtube-disconnect"),
    path("youtube/status/", YouTubeStatusView.as_view(), name="youtube-status"),
    path("threads/connect/", ThreadsConnectView.as_view(), name="threads-connect"),
    path("threads/disconnect/", ThreadsDisconnectView.as_view(), name="threads-disconnect"),
    path("threads/status/", ThreadsStatusView.as_view(), name="threads-status"),
]
