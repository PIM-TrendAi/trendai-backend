"""
Trends app serializers.
"""
from rest_framework import serializers
from .models import Trend, SavedTrend


class TrendSerializer(serializers.ModelSerializer):
    is_saved = serializers.SerializerMethodField()

    class Meta:
        model = Trend
        fields = [
            "id", "hashtag", "platform", "score", "growth", "views",
            "type", "color_start", "color_end", "analysis",
            "target_audience", "avg_video_length", "dominant_format",
            "best_posting_time", "total_views", "total_likes", "total_shares",
            "chart_data", "is_saved", "created_at",
        ]

    def get_is_saved(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return SavedTrend.objects.filter(user=request.user, trend=obj).exists()
        return False


class SavedTrendSerializer(serializers.ModelSerializer):
    trend = TrendSerializer(read_only=True)

    class Meta:
        model = SavedTrend
        fields = ["id", "trend", "saved_at"]
