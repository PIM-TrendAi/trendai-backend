"""
Analytics app — views that aggregate user performance data.
Currently returns carefully seeded dummy data structured for the Flutter charts.
In production, connect to platform OAUTH APIs to fetch real metrics.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from trends.models import SavedTrend


class AnalyticsSummaryView(APIView):
    """GET /api/analytics/summary/ — Overview stats cards."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "total_views": {"value": 24500, "label": "24.5K", "trend": "+15.3%", "direction": "up"},
            "engagement": {"value": 87, "label": "87%", "trend": "+8.7%", "direction": "up"},
            "followers": {"value": 12800, "label": "12.8K", "trend": "+23.1%", "direction": "up"},
            "viral_score": {"value": 94, "label": "94", "trend": "+12.0%", "direction": "up"},
        })


class EngagementView(APIView):
    """GET /api/analytics/engagement/ — 7-day engagement line chart data."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "data": [
                {"day": "Mon", "engagement": 45, "views": 1200},
                {"day": "Tue", "engagement": 52, "views": 1450},
                {"day": "Wed", "engagement": 61, "views": 1680},
                {"day": "Thu", "engagement": 73, "views": 2100},
                {"day": "Fri", "engagement": 85, "views": 2850},
                {"day": "Sat", "engagement": 91, "views": 3200},
                {"day": "Sun", "engagement": 87, "views": 3100},
            ]
        })


class PlatformPerformanceView(APIView):
    """GET /api/analytics/platforms/ — Bar chart data by platform."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "data": [
                {"name": "TikTok", "value": 4200},
                {"name": "Instagram", "value": 3100},
                {"name": "YouTube", "value": 2800},
                {"name": "Facebook", "value": 1900},
            ]
        })


class HeatmapView(APIView):
    """GET /api/analytics/heatmap/ — Best posting-time heatmap (hour × day)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "data": [
                {"hour": "6AM",  "Mon": 2, "Tue": 3, "Wed": 4, "Thu": 5, "Fri": 8, "Sat": 9, "Sun": 7},
                {"hour": "12PM", "Mon": 5, "Tue": 6, "Wed": 7, "Thu": 8, "Fri": 9, "Sat": 8, "Sun": 6},
                {"hour": "6PM",  "Mon": 8, "Tue": 9, "Wed": 9, "Thu": 9, "Fri": 10, "Sat": 9, "Sun": 8},
                {"hour": "12AM", "Mon": 3, "Tue": 4, "Wed": 5, "Thu": 6, "Fri": 7, "Sat": 8, "Sun": 7},
            ]
        })


class SavedTrendAnalyticsView(APIView):
    """GET /api/analytics/saved-trends/ — Saved trends with scores for analytics page."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        saved = SavedTrend.objects.filter(user=request.user).select_related("trend")[:10]
        return Response({
            "data": [
                {"name": st.trend.hashtag, "score": st.trend.score}
                for st in saved
            ]
        })
