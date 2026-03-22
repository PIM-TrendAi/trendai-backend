from django.urls import path
from .views import PlatformListView, PlatformUpdateView

urlpatterns = [
    path("", PlatformListView.as_view(), name="platform-list"),
    path("<int:pk>/", PlatformUpdateView.as_view(), name="platform-update"),
]
