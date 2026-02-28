from django.contrib import admin
from .models import UserPlatform

@admin.register(UserPlatform)
class UserPlatformAdmin(admin.ModelAdmin):
    list_display = ("user", "platform_name", "connected_at")
    search_fields = ("user__email", "platform_name")
    list_filter = ("platform_name",)
    ordering = ("-connected_at",)

