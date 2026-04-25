from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('n8n_integration', '0009_facebook_video_script_fields'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS threads_generated_videos (
                    id BIGSERIAL PRIMARY KEY,
                    post_id VARCHAR(255),
                    user_id VARCHAR(255),
                    niche VARCHAR(255),
                    user_prompt TEXT,
                    script JSONB,
                    script_text TEXT,
                    hook TEXT,
                    body TEXT,
                    cta TEXT,
                    hook_text TEXT,
                    video_prompt TEXT,
                    negative_prompt TEXT,
                    caption TEXT,
                    hashtags TEXT,
                    music_vibe TEXT,
                    title VARCHAR(500),
                    video_url VARCHAR(1000),
                    status VARCHAR(50) NOT NULL DEFAULT 'processing',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS threads_generated_videos;",
        ),
    ]
