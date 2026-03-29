from django.urls import path
from .views import (
    PlatformListView, PlatformUpdateView,
    TikTokInternalTokenView, TikTokDisconnectView, TikTokDebugView,
    InstagramConnectView, InstagramDisconnectView, InstagramStatusView,
)

urlpatterns = [
    path("", PlatformListView.as_view(), name="platform-list"),
    path("<int:pk>/", PlatformUpdateView.as_view(), name="platform-update"),
    path("tiktok/internal-token/", TikTokInternalTokenView.as_view(), name="tiktok-internal-token"),
    path("tiktok/disconnect/", TikTokDisconnectView.as_view(), name="tiktok-disconnect"),
    path("tiktok/debug/", TikTokDebugView.as_view(), name="tiktok-debug"),
    path("instagram/connect/", InstagramConnectView.as_view(), name="instagram-connect"),
    path("instagram/disconnect/", InstagramDisconnectView.as_view(), name="instagram-disconnect"),
    path("instagram/status/", InstagramStatusView.as_view(), name="instagram-status"),
]
