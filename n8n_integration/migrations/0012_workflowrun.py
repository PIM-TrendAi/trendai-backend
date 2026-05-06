from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('n8n_integration', '0011_add_thumbnail_url_to_generated_video'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkflowRun',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('platform', models.CharField(default='tiktok', max_length=50)),
                ('niche', models.CharField(blank=True, max_length=255, null=True)),
                ('status', models.CharField(default='running', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'workflow_runs',
            },
        ),
    ]
