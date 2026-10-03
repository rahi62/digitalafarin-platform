from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("control", "0015_controlled_takeover")]

    operations = [
        migrations.AddField(
            model_name="service",
            name="auto_deploy",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="githubdelivery",
            name="delivery_id",
            field=models.CharField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name="githubdelivery",
            constraint=models.UniqueConstraint(
                fields=("delivery_id", "service"), name="uniq_github_delivery_service"
            ),
        ),
    ]
