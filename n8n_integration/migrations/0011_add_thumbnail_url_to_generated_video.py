# Generated migration to add thumbnail_url to GeneratedVideo

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('n8n_integration', '0010_threads_generated_videos_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='generatedvideo',
            name='thumbnail_url',
            field=models.URLField(blank=True, max_length=1000, null=True),
        ),
    ]
