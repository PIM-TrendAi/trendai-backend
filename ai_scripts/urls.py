from django.urls import path
from .views import (
    GenerateScriptView, SavedScriptListView,
    GeneratedVideoListView, VideoGenerateTriggerView,
    VideoApproveView, VideoRejectView, VideoPublishView,
)

urlpatterns = [
    path("", SavedScriptListView.as_view(), name="script-list"),
    path("generate/", GenerateScriptView.as_view(), name="script-generate"),
    path("videos/", GeneratedVideoListView.as_view(), name="video-list"),
    path("videos/generate/", VideoGenerateTriggerView.as_view(), name="video-generate"),
    path("videos/<int:pk>/approve/", VideoApproveView.as_view(), name="video-approve"),
    path("videos/<int:pk>/reject/", VideoRejectView.as_view(), name="video-reject"),
    path("videos/<int:pk>/publish/", VideoPublishView.as_view(), name="video-publish"),
]
