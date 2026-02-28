from django.urls import path
from .views import TrendListView, TrendDetailView, SaveTrendView, SavedTrendListView

urlpatterns = [
    path("", TrendListView.as_view(), name="trend-list"),
    path("saved/", SavedTrendListView.as_view(), name="saved-trends"),
    path("<int:pk>/", TrendDetailView.as_view(), name="trend-detail"),
    path("<int:pk>/save/", SaveTrendView.as_view(), name="trend-save"),
]
