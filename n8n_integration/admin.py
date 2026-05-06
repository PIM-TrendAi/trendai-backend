from django.contrib import admin
from .models import TrendingVideo, CreatorSession, GeneratedScript, GeneratedVideo, PostedVideo, ConnectedPlatform

@admin.register(TrendingVideo)
class TrendingVideoAdmin(admin.ModelAdmin):
    list_display = ("rank", "title", "author", "views", "scraped_at")
    search_fields = ("title", "author", "video_id")
    list_filter = ("category", "scraped_at")

@admin.register(CreatorSession)
class CreatorSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "creator_id", "niche", "status", "created_at")
    search_fields = ("session_id", "creator_id", "niche")
    list_filter = ("status", "created_at")

@admin.register(GeneratedScript)
class GeneratedScriptAdmin(admin.ModelAdmin):
    list_display = ("script_id", "session_id", "creator_id", "status", "created_at")
    search_fields = ("script_id", "session_id", "creator_id")
    list_filter = ("status", "created_at")

@admin.register(GeneratedVideo)
class GeneratedVideoAdmin(admin.ModelAdmin):
    list_display = ("video_id", "session_id", "creator_id", "status", "created_at")
    search_fields = ("video_id", "session_id", "creator_id")
    list_filter = ("status", "created_at")

@admin.register(PostedVideo)
class PostedVideoAdmin(admin.ModelAdmin):
    list_display = ("session_id", "creator_id", "posted_at", "tiktok_post_id")
    search_fields = ("session_id", "creator_id", "tiktok_post_id")
    list_filter = ("posted_at",)

@admin.register(ConnectedPlatform)
class ConnectedPlatformAdmin(admin.ModelAdmin):
    list_display = ("creator_id", "platform_name", "created_at")
    search_fields = ("creator_id", "platform_name")
    list_filter = ("platform_name", "created_at")
