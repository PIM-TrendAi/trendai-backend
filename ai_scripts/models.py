"""
AI Scripts app — model, serializer, views for generating and saving scripts.
Script generation returns a deterministic structured response (mocked AI).
In production, replace generate_script() with an OpenAI/Gemini API call.
"""
from django.db import models
from django.conf import settings


class AIScript(models.Model):
    """A user-generated AI content script."""

    STYLE_CHOICES = [
        ("Funny", "Funny"),
        ("Informative", "Informative"),
        ("Dramatic", "Dramatic"),
        ("Casual", "Casual"),
    ]
    DURATION_CHOICES = [
        ("30s", "30 seconds"),
        ("60s", "60 seconds"),
        ("90s", "90 seconds"),
    ]
    PLATFORM_CHOICES = [
        ("TikTok", "TikTok"),
        ("Instagram", "Instagram"),
        ("YouTube", "YouTube"),
        ("Facebook", "Facebook"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scripts")
    prompt = models.TextField()
    style = models.CharField(max_length=20, choices=STYLE_CHOICES, default="Informative")
    duration = models.CharField(max_length=5, choices=DURATION_CHOICES, default="60s")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default="TikTok")
    # Generated output
    hook = models.TextField(blank=True)
    script = models.TextField(blank=True)
    cta = models.TextField(blank=True)
    hashtags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_scripts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} — {self.prompt[:60]}"
