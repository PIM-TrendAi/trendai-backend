from django.urls import path
from .views import PlatformListView, PlatformUpdateView, TikTokInternalTokenView, TikTokDisconnectView, TikTokDebugView

urlpatterns = [
    path("", PlatformListView.as_view(), name="platform-list"),
    path("<int:pk>/", PlatformUpdateView.as_view(), name="platform-update"),
    path("tiktok/internal-token/", TikTokInternalTokenView.as_view(), name="tiktok-internal-token"),
    path("tiktok/disconnect/", TikTokDisconnectView.as_view(), name="tiktok-disconnect"),
    path("tiktok/debug/", TikTokDebugView.as_view(), name="tiktok-debug"),
]
