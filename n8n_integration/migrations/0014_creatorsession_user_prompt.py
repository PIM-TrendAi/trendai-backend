from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('n8n_integration', '0013_instagramreel'),
    ]

    operations = [
        migrations.AddField(
            model_name='creatorsession',
            name='user_prompt',
            field=models.TextField(blank=True, null=True),
        ),
    ]
