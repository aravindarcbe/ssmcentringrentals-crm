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
        ("rentals", "0005_rate_units_and_damage_charge"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialcategory",
            name="default_rate_unit",
            field=models.CharField(
                choices=RATE_UNIT_CHOICES,
                default="FLAT_FT",
                help_text="Prefills the rate unit when adding a new material under this category",
                max_length=12,
            ),
        ),
    ]
