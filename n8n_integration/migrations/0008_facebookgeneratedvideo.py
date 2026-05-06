from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('n8n_integration', '0007_add_audio_url_is_fallback_to_generated_video'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Update model state for audio_url and is_fallback (already in DB via RunSQL in 0007)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='generatedvideo',
                    name='audio_url',
                    field=models.URLField(blank=True, max_length=1000, null=True),
                ),
                migrations.AddField(
                    model_name='generatedvideo',
                    name='is_fallback',
                    field=models.BooleanField(default=False),
                ),
            ],
            database_operations=[],  # Already applied via RunSQL in 0007
        ),
        # Create facebook_generated_videos table using IF NOT EXISTS to be safe
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS facebook_generated_videos (
                    id BIGSERIAL PRIMARY KEY,
                    reel_id VARCHAR(255) NOT NULL,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    niche VARCHAR(255),
                    user_prompt TEXT,
                    script JSONB,
                    script_text TEXT,
                    video_url VARCHAR(1000),
                    status VARCHAR(50) NOT NULL DEFAULT 'processing',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS facebook_generated_videos;",
        ),
        # Register the model in Django's state
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='FacebookGeneratedVideo',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('reel_id', models.CharField(max_length=255)),
                        ('niche', models.CharField(blank=True, max_length=255, null=True)),
                        ('user_prompt', models.TextField(blank=True, null=True)),
                        ('script', models.JSONField(blank=True, null=True)),
                        ('script_text', models.TextField(blank=True, null=True)),
                        ('video_url', models.URLField(blank=True, max_length=1000, null=True)),
                        ('status', models.CharField(default='processing', max_length=50)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'facebook_generated_videos',
                    },
                ),
            ],
            database_operations=[],  # Already done via RunSQL above
        ),
    ]
