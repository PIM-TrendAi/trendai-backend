from django.urls import path
from .views import (
    TrendingVideoListView,
    SessionStatusView,
    StartWorkflowView,
    GetLatestSessionView,
    ApproveScriptView,
    ApproveVideoView,
    TriggerScrapingView,
    GeneratedVideosListView,
    ConnectedPlatformsView,
    PlatformAuthURLView,
    PlatformCallbackView,
)

urlpatterns = [
    path('trending_videos/', TrendingVideoListView.as_view(), name='trending-videos-list'),
    path('sessions/latest/', GetLatestSessionView.as_view(), name='get-latest-session'),
    path('sessions/<str:session_id>/', SessionStatusView.as_view(), name='get-session-status'),
    path('start/', StartWorkflowView.as_view(), name='start-workflow'),
    path('approve/script/', ApproveScriptView.as_view(), name='approve-script'),
    path('approve/video/', ApproveVideoView.as_view(), name='approve-video'),
    path('trigger-scrape/', TriggerScrapingView.as_view(), name='trigger-scrape'),
    path('my-videos/', GeneratedVideosListView.as_view(), name='my-videos'),
    
    path('platforms/', ConnectedPlatformsView.as_view(), name='connected-platforms'),
    path('platforms/<str:platform>/url/', PlatformAuthURLView.as_view(), name='platform-auth-url'),
    path('platforms/<str:platform>/callback/', PlatformCallbackView.as_view(), name='platform-callback'),
]
