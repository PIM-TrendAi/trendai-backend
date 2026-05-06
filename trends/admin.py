from django.contrib import admin
from .models import Trend, SavedTrend

@admin.register(Trend)
class TrendAdmin(admin.ModelAdmin):
    list_display = ("hashtag", "platform", "type", "score", "growth", "created_at")
    search_fields = ("hashtag", "platform")
    list_filter = ("platform", "type")
    ordering = ("-score",)

@admin.register(SavedTrend)
class SavedTrendAdmin(admin.ModelAdmin):
    list_display = ("user", "trend", "saved_at")
    search_fields = ("user__email", "trend__hashtag")
    ordering = ("-saved_at",)

