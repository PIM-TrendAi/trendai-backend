from django.contrib import admin
from .models import AIScript

@admin.register(AIScript)
class AIScriptAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "style", "duration", "created_at")
    search_fields = ("user__email", "prompt", "platform")
    list_filter = ("platform", "style", "duration")
    ordering = ("-created_at",)

