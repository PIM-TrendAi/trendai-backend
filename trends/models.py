"""
Trends app models.
- Trend: a viral hashtag/audio/video trend across platforms
- SavedTrend: user bookmarks on trends
"""
from django.db import models
from django.conf import settings


class Trend(models.Model):
    """A viral trend item scraped from social platforms."""

    PLATFORM_CHOICES = [
        ("TikTok", "TikTok"),
        ("Instagram", "Instagram"),
        ("YouTube", "YouTube"),
        ("Facebook", "Facebook"),
        ("X", "X"),
    ]
    TYPE_CHOICES = [
        ("hashtag", "Hashtag"),
        ("audio", "Audio"),
        ("video", "Video"),
    ]

    hashtag = models.CharField(max_length=255, db_index=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, db_index=True)
    score = models.FloatField(default=0.0)   # Trend score 0-100
    growth = models.FloatField(default=0.0)  # Growth % over 7 days
    views = models.CharField(max_length=20, default="0")  # Human-readable e.g. "2.4M"
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="hashtag")
    color_start = models.CharField(max_length=30, default="#6C5CE7")
    color_end = models.CharField(max_length=30, default="#00C6FF")
    # Why it's working analysis
    analysis = models.JSONField(default=list, blank=True)
    # Content stats
    target_audience = models.CharField(max_length=100, default="General")
    avg_video_length = models.CharField(max_length=50, default="30-60 seconds")
    dominant_format = models.CharField(max_length=100, default="Entertainment")
    best_posting_time = models.CharField(max_length=50, default="6-8 PM")
    # Engagement counts
    total_views = models.BigIntegerField(default=0)
    total_likes = models.BigIntegerField(default=0)
    total_shares = models.BigIntegerField(default=0)
    # Chart data (7-day evolution)
    chart_data = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trends"
        indexes = [
            models.Index(fields=["platform"]),
            models.Index(fields=["-score"]),
            models.Index(fields=["-growth"]),
        ]
        ordering = ["-score"]

    def __str__(self):
        return f"{self.hashtag} ({self.platform})"


class SavedTrend(models.Model):
    """User bookmarks on trends."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_trends")
    trend = models.ForeignKey(Trend, on_delete=models.CASCADE, related_name="savers")
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "saved_trends"
        unique_together = [("user", "trend")]
        ordering = ["-saved_at"]

    def __str__(self):
        return f"{self.user.email} → {self.trend.hashtag}"
