"""
Platforms app — tracks which social media platforms a user has connected.
"""
from django.db import models
from django.conf import settings


class UserPlatform(models.Model):
    """Tracks which social media platforms a user has connected."""

    PLATFORM_CHOICES = [
        ("TikTok", "TikTok"),
        ("Instagram", "Instagram"),
        ("YouTube", "YouTube"),
        ("Facebook", "Facebook"),
        ("X", "X"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="platforms")
    platform_name = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    connected = models.BooleanField(default=False)
    connected_at = models.DateTimeField(null=True, blank=True)
    access_token = models.TextField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_platforms"
        unique_together = [("user", "platform_name")]

    def __str__(self):
        status = "connected" if self.connected else "disconnected"
        return f"{self.user.email} — {self.platform_name} ({status})"
