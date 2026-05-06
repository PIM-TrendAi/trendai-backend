from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platforms", "0002_userplatform_access_token_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userplatform",
            name="refresh_token",
            field=models.TextField(blank=True, null=True),
        ),
    ]