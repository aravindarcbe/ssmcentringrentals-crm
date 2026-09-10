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
from .utils import format_amount


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
    list_display = ("category", "size_label", "ft_value", "rate_display", "available_count", "total_stock_count")
    list_filter = ("category",)
    search_fields = ("size_label",)

    @admin.display(description="Rate/day")
    def rate_display(self, obj):
        return format_amount(obj.default_rate_per_day)


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
    list_display = ("invoice_number", "customer", "date_out", "status", "bill_display", "net_position_display")
    list_filter = ("status",)
    search_fields = ("invoice_number", "customer__name")
    inlines = [RentalLineItemInline, DepositLedgerInline, ReceiptInline]

    @admin.display(description="Total bill")
    def bill_display(self, obj):
        return format_amount(obj.total_bill_amount)

    @admin.display(description="Net position")
    def net_position_display(self, obj):
        return format_amount(obj.net_position)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("date", "description", "payee", "amount_display", "payment_mode")
    list_filter = ("payment_mode",)
    search_fields = ("description", "payee")

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return format_amount(obj.amount)


@admin.register(ProductPurchase)
class ProductPurchaseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "size_label", "count", "rate_display", "amount_display")
    list_filter = ("category",)

    @admin.display(description="Rate")
    def rate_display(self, obj):
        return format_amount(obj.rate)

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return format_amount(obj.amount)


@admin.register(DailyExpense)
class DailyExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "description", "amount_display", "payment_mode")
    list_filter = ("category", "payment_mode")
    search_fields = ("category", "description")

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return format_amount(obj.amount)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("date", "material", "transaction", "direction", "count")
    list_filter = ("direction",)
