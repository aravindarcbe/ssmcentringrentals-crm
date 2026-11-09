from django.db import models
from django.core.validators import MinValueValidator


PAYMENT_MODE_CHOICES = [
    ("CASH", "Cash"),
    ("GPAY", "GPay"),
    ("CARD", "Card"),
    ("BANK", "Bank transfer"),
]

# RATE_UNIT_FLAT_FT is the legacy/default behavior (ft_value * rate * count, no day
# multiplier) — matches the already-resolved billing formula in spec.md §3.1, so
# every existing Material/RentalLineItem keeps computing the same amount it always
# did. The other units are new, opt-in, and actually factor in days_estimated.
RATE_UNIT_FLAT_FT = "FLAT_FT"
RATE_UNIT_PIECE_DAY = "PIECE_DAY"
RATE_UNIT_FT_DAY = "FT_DAY"
RATE_UNIT_PIECE_20D = "PIECE_20D"
RATE_UNIT_FT_20D = "FT_20D"
RATE_UNIT_PIECE_30D = "PIECE_30D"
RATE_UNIT_CHOICES = [
    (RATE_UNIT_FLAT_FT, "Per ft (flat — existing default)"),
    (RATE_UNIT_PIECE_DAY, "Per piece / day"),
    (RATE_UNIT_FT_DAY, "Per ft / day"),
    (RATE_UNIT_PIECE_20D, "Per piece / 20 days"),
    (RATE_UNIT_FT_20D, "Per ft / 20 days"),
    (RATE_UNIT_PIECE_30D, "Per piece / 30 days"),
]


class Customer(models.Model):
    TYPE_CONTRACTOR = "CONTRACTOR"
    TYPE_BUILDER = "BUILDER"
    TYPE_OWNER = "OWNER"
    TYPE_MASON = "MASON"
    TYPE_CHOICES = [
        (TYPE_CONTRACTOR, "Contractor"),
        (TYPE_BUILDER, "Builder"),
        (TYPE_OWNER, "Owner"),
        (TYPE_MASON, "Mason"),
    ]

    customer_id = models.CharField(max_length=20, unique=True, blank=True, help_text="Auto-generated, e.g. SSM-CUS-0001")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    place = models.CharField(max_length=200, blank=True)
    address = models.CharField(max_length=255, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    construction_site_address = models.CharField(max_length=255, blank=True)
    customer_type = models.CharField(max_length=20, choices=TYPE_CHOICES, blank=True)
    payment_terms = models.CharField(max_length=255, blank=True, help_text="e.g. \"Rent ₹500/day, Advance ₹5000\"")
    aadhar_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MaterialCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Material categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Material(models.Model):
    category = models.ForeignKey(MaterialCategory, on_delete=models.PROTECT, related_name="materials")
    size_label = models.CharField(max_length=100, help_text='e.g. "12 inch 8 ft"')
    ft_value = models.DecimalField(max_digits=8, decimal_places=2, help_text="Length in feet, used in bill amount calc")
    default_rate_per_day = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    rate_unit = models.CharField(
        max_length=12, choices=RATE_UNIT_CHOICES, default=RATE_UNIT_FLAT_FT,
        help_text="How the rate is quoted — prefills new rental line items for this material",
    )
    total_stock_count = models.PositiveIntegerField(default=0)
    available_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["category__name", "size_label"]

    def __str__(self):
        return f"{self.category.name} - {self.size_label}"


class RentalTransaction(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_PARTIAL = "PARTIALLY_RETURNED"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_PARTIAL, "Partially returned"),
        (STATUS_CLOSED, "Closed"),
    ]

    invoice_number = models.CharField(max_length=30, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="rental_transactions")
    date_out = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transportation = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Transportation charge shown on the invoice")
    damage_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Charge for damaged materials, shown on the invoice")
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_out", "-id"]

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"

    @property
    def total_bill_amount(self):
        return sum((item.line_amount for item in self.line_items.all()), start=0)

    @property
    def total_deposit_collected(self):
        return sum((d.amount_collected for d in self.deposit_entries.all()), start=0)

    @property
    def total_deposit_refunded(self):
        return sum((d.amount_refunded for d in self.deposit_entries.all()), start=0)

    @property
    def total_received(self):
        return sum((r.amount for r in self.receipts.all()), start=0)

    @property
    def deposit_held(self):
        return self.total_deposit_collected - self.total_deposit_refunded

    @property
    def net_position(self):
        """Positive = refund due to customer, negative = balance due from customer."""
        return (self.total_deposit_collected - self.total_deposit_refunded) - self.total_bill_amount - self.discount

    @property
    def invoice_subtotal(self):
        return self.total_bill_amount - self.discount

    @property
    def grand_total(self):
        """Subtotal + Transportation + Damage charge, as shown on the printed
        invoice (§6/§7 of docs/change-requests-2026-11.md) — not part of
        net_position's own deposit/balance math, which is unchanged."""
        return self.invoice_subtotal + self.transportation + self.damage_charge


class RentalLineItem(models.Model):
    transaction = models.ForeignKey(RentalTransaction, on_delete=models.CASCADE, related_name="line_items")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="rental_lines")
    count = models.PositiveIntegerField()
    days_estimated = models.PositiveIntegerField(default=1)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    rate_unit = models.CharField(max_length=12, choices=RATE_UNIT_CHOICES, default=RATE_UNIT_FLAT_FT)
    count_returned = models.PositiveIntegerField(default=0)
    date_returned = models.DateField(null=True, blank=True)
    days_actual = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.material} x{self.count} ({self.transaction.invoice_number})"

    @property
    def line_amount(self):
        """Bill amount, fixed at creation time (days_estimated, not actual return
        days — see spec.md §3.1). FLAT_FT reproduces the original, always-resolved
        formula (Ft x Rate x Count, no day multiplier) so nothing created before
        rate units existed changes. The other units actually factor in days."""
        from math import ceil

        ft = self.material.ft_value or 0
        days = self.days_estimated or 1

        if self.rate_unit == RATE_UNIT_PIECE_DAY:
            return self.rate * self.count * days
        if self.rate_unit == RATE_UNIT_FT_DAY:
            return self.rate * ft * self.count * days
        if self.rate_unit == RATE_UNIT_PIECE_20D:
            return self.rate * self.count * ceil(days / 20)
        if self.rate_unit == RATE_UNIT_FT_20D:
            return self.rate * ft * self.count * ceil(days / 20)
        if self.rate_unit == RATE_UNIT_PIECE_30D:
            return self.rate * self.count * ceil(days / 30)
        return ft * self.rate * self.count  # RATE_UNIT_FLAT_FT

    @property
    def is_fully_returned(self):
        return self.count_returned >= self.count

    @property
    def due_date(self):
        """Expected return date — date_out + days_estimated. Not stored; computed
        the same way line_amount is, so there's nothing to keep in sync."""
        from datetime import timedelta
        return self.transaction.date_out + timedelta(days=self.days_estimated)


class DepositLedger(models.Model):
    transaction = models.ForeignKey(RentalTransaction, on_delete=models.CASCADE, related_name="deposit_entries")
    date = models.DateField()
    amount_collected = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_refunded = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Deposit entry for {self.transaction.invoice_number}"


class Receipt(models.Model):
    transaction = models.ForeignKey(RentalTransaction, on_delete=models.CASCADE, related_name="receipts")
    date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, default="CASH")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Receipt {self.amount} - {self.transaction.invoice_number}"


class Payment(models.Model):
    date = models.DateField()
    description = models.CharField(max_length=255)
    payee = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, default="CASH")

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.description} - {self.amount}"


class PurchaseBill(models.Model):
    """Header for a vendor purchase bill — one bill can list several line items."""

    bill_number = models.CharField(max_length=30, unique=True)
    date = models.DateField()
    vendor_name = models.CharField(max_length=200, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.bill_number} - {self.vendor_name or 'purchase'}"

    @property
    def total_amount(self):
        return sum((line.amount for line in self.line_items.all()), start=0)


class ProductPurchase(models.Model):
    bill = models.ForeignKey(PurchaseBill, on_delete=models.CASCADE, related_name="line_items")
    date = models.DateField()
    category = models.ForeignKey(MaterialCategory, on_delete=models.PROTECT, related_name="purchases")
    size_label = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255, blank=True, help_text="Free-text notes, e.g. from an imported vendor bill")
    count = models.PositiveIntegerField()
    rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.category} purchase - {self.amount}"


class DailyExpense(models.Model):
    date = models.DateField()
    category = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, default="CASH")

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.category} - {self.amount}"


class StockMovement(models.Model):
    DIRECTION_OUT = "OUT"
    DIRECTION_IN = "IN"
    DIRECTION_CHOICES = [
        (DIRECTION_OUT, "Out (rented)"),
        (DIRECTION_IN, "In (returned)"),
    ]

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="stock_movements")
    transaction = models.ForeignKey(RentalTransaction, on_delete=models.CASCADE, related_name="stock_movements")
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    count = models.PositiveIntegerField()
    date = models.DateField()

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.direction} {self.count} x {self.material} ({self.transaction.invoice_number})"
