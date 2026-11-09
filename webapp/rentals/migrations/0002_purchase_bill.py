from django.db import migrations, models
import django.db.models.deletion


def backfill_purchase_bills(apps, schema_editor):
    """Wrap every pre-existing ProductPurchase row in its own single-line bill,
    so the new required `bill` FK has something to point at."""
    ProductPurchase = apps.get_model("rentals", "ProductPurchase")
    PurchaseBill = apps.get_model("rentals", "PurchaseBill")

    for pp in ProductPurchase.objects.filter(bill__isnull=True).order_by("id"):
        bill = PurchaseBill.objects.create(
            bill_number=f"SSM/PUR/LEGACY-{pp.id:04d}",
            date=pp.date,
            remarks="Auto-created for a purchase row that predates multi-item bills.",
        )
        pp.bill = bill
        pp.save(update_fields=["bill"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rentals", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseBill",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("bill_number", models.CharField(max_length=30, unique=True)),
                ("date", models.DateField()),
                ("vendor_name", models.CharField(blank=True, max_length=200)),
                ("remarks", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.AddField(
            model_name="productpurchase",
            name="description",
            field=models.CharField(
                blank=True,
                help_text="Free-text notes, e.g. from an imported vendor bill",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="productpurchase",
            name="bill",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="line_items",
                to="rentals.purchasebill",
            ),
        ),
        migrations.RunPython(backfill_purchase_bills, noop_reverse),
        migrations.AlterField(
            model_name="productpurchase",
            name="bill",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="line_items",
                to="rentals.purchasebill",
            ),
        ),
    ]
