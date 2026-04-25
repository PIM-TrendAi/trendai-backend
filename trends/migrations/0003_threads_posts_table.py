from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trends', '0002_facebookreel_youtubevideo'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS threads_posts (
                    id BIGSERIAL PRIMARY KEY,
                    post_id TEXT UNIQUE NOT NULL,
                    post_url TEXT,
                    profile_url TEXT,
                    username TEXT,
                    text TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    like_count INTEGER NOT NULL DEFAULT 0,
                    reply_count INTEGER NOT NULL DEFAULT 0,
                    repost_count INTEGER NOT NULL DEFAULT 0,
                    has_video BOOLEAN NOT NULL DEFAULT FALSE,
                    video_url TEXT,
                    thumbnail_url TEXT,
                    niche TEXT,
                    status TEXT NOT NULL DEFAULT 'scraped'
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS threads_posts;",
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='ThreadsPost',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('post_id', models.TextField(unique=True)),
                        ('post_url', models.TextField(blank=True, null=True)),
                        ('profile_url', models.TextField(blank=True, null=True)),
                        ('username', models.TextField(blank=True, null=True)),
                        ('text', models.TextField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(blank=True, null=True)),
                        ('like_count', models.IntegerField(default=0)),
                        ('reply_count', models.IntegerField(default=0)),
                        ('repost_count', models.IntegerField(default=0)),
                        ('has_video', models.BooleanField(default=False)),
                        ('video_url', models.TextField(blank=True, null=True)),
                        ('thumbnail_url', models.TextField(blank=True, null=True)),
                        ('niche', models.TextField(blank=True, null=True)),
                        ('status', models.TextField(default='scraped')),
                    ],
                    options={
                        'db_table': 'threads_posts',
                        'ordering': ['-like_count'],
                        'managed': False,
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
