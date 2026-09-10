from django.contrib import admin

from .models import (
    Customer,
    MaterialCategory,
    Material,
    RentalTransaction,
    RentalLineItem,
    DepositLedger,
    Receipt,
    Payment,
    ProductPurchase,
    DailyExpense,
    StockMovement,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "place", "created_at")
    search_fields = ("name", "phone", "place")


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("category", "size_label", "ft_value", "default_rate_per_day", "available_count", "total_stock_count")
    list_filter = ("category",)
    search_fields = ("size_label",)


class RentalLineItemInline(admin.TabularInline):
    model = RentalLineItem
    extra = 1


class DepositLedgerInline(admin.TabularInline):
    model = DepositLedger
    extra = 1


class ReceiptInline(admin.TabularInline):
    model = Receipt
    extra = 1


@admin.register(RentalTransaction)
class RentalTransactionAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "date_out", "status", "total_bill_amount", "net_position")
    list_filter = ("status",)
    search_fields = ("invoice_number", "customer__name")
    inlines = [RentalLineItemInline, DepositLedgerInline, ReceiptInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("date", "description", "payee", "amount", "payment_mode")
    list_filter = ("payment_mode",)
    search_fields = ("description", "payee")


@admin.register(ProductPurchase)
class ProductPurchaseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "size_label", "count", "rate", "amount")
    list_filter = ("category",)


@admin.register(DailyExpense)
class DailyExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "description", "amount", "payment_mode")
    list_filter = ("category", "payment_mode")
    search_fields = ("category", "description")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("date", "material", "transaction", "direction", "count")
    list_filter = ("direction",)
