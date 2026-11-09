from django.db import migrations, models


def backfill_customer_ids(apps, schema_editor):
    Customer = apps.get_model("rentals", "Customer")
    for i, customer in enumerate(Customer.objects.filter(customer_id__isnull=True).order_by("id"), start=1):
        customer.customer_id = f"SSM-CUS-{i:04d}"
        customer.save(update_fields=["customer_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("rentals", "0002_purchase_bill"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="customer_id",
            field=models.CharField(
                blank=True,
                help_text="Auto-generated, e.g. SSM-CUS-0001",
                max_length=20,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="address",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="pincode",
            field=models.CharField(blank=True, default="", max_length=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="construction_site_address",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="customer_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CONTRACTOR", "Contractor"),
                    ("BUILDER", "Builder"),
                    ("OWNER", "Owner"),
                    ("MASON", "Mason"),
                ],
                default="",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="payment_terms",
            field=models.CharField(
                blank=True,
                default="",
                help_text='e.g. "Rent ₹500/day, Advance ₹5000"',
                max_length=255,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_customer_ids, noop_reverse),
        migrations.AlterField(
            model_name="customer",
            name="customer_id",
            field=models.CharField(
                blank=True,
                help_text="Auto-generated, e.g. SSM-CUS-0001",
                max_length=20,
                unique=True,
            ),
        ),
    ]
