from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rentals", "0003_customer_profile_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentaltransaction",
            name="transportation",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Transportation charge shown on the invoice",
                max_digits=10,
            ),
        ),
    ]
