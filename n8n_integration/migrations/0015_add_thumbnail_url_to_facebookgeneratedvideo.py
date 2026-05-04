from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('n8n_integration', '0014_creatorsession_user_prompt'),
    ]

    operations = [
        migrations.AddField(
            model_name='facebookgeneratedvideo',
            name='thumbnail_url',
            field=models.URLField(blank=True, max_length=1000, null=True),
        ),
    ]
