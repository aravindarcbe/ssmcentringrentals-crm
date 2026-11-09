from django.db import migrations, models

RATE_UNIT_CHOICES = [
    ("FLAT_FT", "Per ft (flat — existing default)"),
    ("PIECE_DAY", "Per piece / day"),
    ("FT_DAY", "Per ft / day"),
    ("PIECE_20D", "Per piece / 20 days"),
    ("FT_20D", "Per ft / 20 days"),
    ("PIECE_30D", "Per piece / 30 days"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("rentals", "0004_rentaltransaction_transportation"),
    ]

    operations = [
        migrations.AddField(
            model_name="material",
            name="rate_unit",
            field=models.CharField(
                choices=RATE_UNIT_CHOICES,
                default="FLAT_FT",
                help_text="How the rate is quoted — prefills new rental line items for this material",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="rentallineitem",
            name="rate_unit",
            field=models.CharField(choices=RATE_UNIT_CHOICES, default="FLAT_FT", max_length=12),
        ),
        migrations.AddField(
            model_name="rentaltransaction",
            name="damage_charge",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Charge for damaged materials, shown on the invoice",
                max_digits=10,
            ),
        ),
    ]
