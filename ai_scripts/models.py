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


class GeneratedVideo(models.Model):
    """
    Mapped to the generated_videos table populated by the n8n video generation workflow.
    Managed=False prevents Django from altering the schema, as it's owned by the SQL migration.
    """
    reel = models.ForeignKey(
        'trends.FacebookReel', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        db_column='reel_id', 
        to_field='reel_id'
    )
    user_id_str = models.CharField(max_length=50, db_column='user_id', null=True, blank=True)
    niche = models.TextField(null=True, blank=True)
    user_prompt = models.TextField(null=True, blank=True)
    script = models.TextField(null=True, blank=True)
    script_text = models.TextField(null=True, blank=True)
    fal_request_id = models.TextField(null=True, blank=True)
    video_url = models.TextField(null=True, blank=True)
    status = models.TextField(default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "generated_videos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Video {self.id} - Status: {self.status}"
    
    @property
    def user(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if self.user_id_str and self.user_id_str.isdigit():
            return User.objects.filter(id=int(self.user_id_str)).first()
        return None
