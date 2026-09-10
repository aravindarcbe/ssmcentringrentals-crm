"""One-off script to load sample data so the dashboard has something to show.
Run with: python manage.py shell < seed_demo_data.py
Safe to delete once real data entry begins.
"""
import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ssm_crm.settings")
django.setup()

from datetime import date, timedelta
from rentals.models import (
    Customer,
    MaterialCategory,
    Material,
    RentalTransaction,
    RentalLineItem,
    DepositLedger,
    Receipt,
    Payment,
    DailyExpense,
    ProductPurchase,
)

jockey_cat, _ = MaterialCategory.objects.get_or_create(name="Jockey")
sheet_cat, _ = MaterialCategory.objects.get_or_create(name="Sheet")
runner_cat, _ = MaterialCategory.objects.get_or_create(name="Runner")

m1, _ = Material.objects.get_or_create(
    category=jockey_cat, size_label="8 ft", defaults=dict(ft_value=8, default_rate_per_day=80, total_stock_count=50, available_count=35)
)
m2, _ = Material.objects.get_or_create(
    category=sheet_cat, size_label="Standard", defaults=dict(ft_value=25, default_rate_per_day=35, total_stock_count=100, available_count=75)
)
m3, _ = Material.objects.get_or_create(
    category=runner_cat, size_label="6 ft", defaults=dict(ft_value=6, default_rate_per_day=18, total_stock_count=40, available_count=3)
)

c1, _ = Customer.objects.get_or_create(name="Loganathan", defaults=dict(phone="9176038740", place="Chennai"))
c2, _ = Customer.objects.get_or_create(name="Sridhar", defaults=dict(phone="9952970295", place="Chennai"))

today = date.today()

t1, created = RentalTransaction.objects.get_or_create(
    invoice_number="SSM/INV/DEMO-001",
    defaults=dict(customer=c1, date_out=today - timedelta(days=5), status=RentalTransaction.STATUS_OPEN),
)
if created:
    RentalLineItem.objects.create(transaction=t1, material=m2, count=25, days_estimated=21, rate=35)
    RentalLineItem.objects.create(transaction=t1, material=m1, count=15, days_estimated=21, rate=80)
    DepositLedger.objects.create(transaction=t1, date=t1.date_out, amount_collected=2075)
    Receipt.objects.create(transaction=t1, date=t1.date_out, amount=2075, payment_mode="GPAY")

t2, created = RentalTransaction.objects.get_or_create(
    invoice_number="SSM/INV/DEMO-002",
    defaults=dict(customer=c2, date_out=today - timedelta(days=2), status=RentalTransaction.STATUS_CLOSED),
)
if created:
    RentalLineItem.objects.create(transaction=t2, material=m1, count=8, days_estimated=3, rate=8, count_returned=8, date_returned=today)
    DepositLedger.objects.create(transaction=t2, date=t2.date_out, amount_collected=2000)
    DepositLedger.objects.create(transaction=t2, date=today, amount_refunded=1488)
    Receipt.objects.create(transaction=t2, date=t2.date_out, amount=450, payment_mode="GPAY")

Payment.objects.get_or_create(date=today - timedelta(days=3), description="Salary", payee="Sathish", amount=12000, payment_mode="BANK")
DailyExpense.objects.get_or_create(date=today - timedelta(days=1), category="Petrol", description="Official", amount=370, payment_mode="GPAY")
ProductPurchase.objects.get_or_create(date=today - timedelta(days=10), category=jockey_cat, size_label="8 ft", count=20, defaults=dict(rate=1750, amount=35000))

print("Demo data loaded.")
