from django.db import models
from django.core.validators import MinValueValidator


PAYMENT_MODE_CHOICES = [
    ("CASH", "Cash"),
    ("GPAY", "GPay"),
    ("CARD", "Card"),
    ("BANK", "Bank transfer"),
]


class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    place = models.CharField(max_length=200, blank=True)
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
    def net_position(self):
        """Positive = refund due to customer, negative = balance due from customer."""
        return (self.total_deposit_collected - self.total_deposit_refunded) - self.total_bill_amount - self.discount


class RentalLineItem(models.Model):
    transaction = models.ForeignKey(RentalTransaction, on_delete=models.CASCADE, related_name="line_items")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="rental_lines")
    count = models.PositiveIntegerField()
    days_estimated = models.PositiveIntegerField(default=1)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    count_returned = models.PositiveIntegerField(default=0)
    date_returned = models.DateField(null=True, blank=True)
    days_actual = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.material} x{self.count} ({self.transaction.invoice_number})"

    @property
    def line_amount(self):
        """Matches the source sheet convention: Ft x Rate x Count."""
        return (self.material.ft_value or 0) * self.rate * self.count

    @property
    def is_fully_returned(self):
        return self.count_returned >= self.count


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


class ProductPurchase(models.Model):
    date = models.DateField()
    category = models.ForeignKey(MaterialCategory, on_delete=models.PROTECT, related_name="purchases")
    size_label = models.CharField(max_length=100, blank=True)
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
