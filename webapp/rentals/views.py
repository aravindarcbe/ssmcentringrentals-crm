from datetime import date

from django.db.models import Sum, F
from django.shortcuts import render

from .models import (
    Material,
    RentalTransaction,
    Receipt,
    Payment,
    DailyExpense,
    ProductPurchase,
    DepositLedger,
)


def dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)

    cash_in = Receipt.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0

    payments_out = Payment.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    expenses_out = DailyExpense.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    purchases_out = ProductPurchase.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    cash_out = payments_out + expenses_out + purchases_out

    deposits_collected = DepositLedger.objects.aggregate(total=Sum("amount_collected"))["total"] or 0
    deposits_refunded = DepositLedger.objects.aggregate(total=Sum("amount_refunded"))["total"] or 0
    deposits_held = deposits_collected - deposits_refunded

    open_transactions = RentalTransaction.objects.exclude(status=RentalTransaction.STATUS_CLOSED)
    pending_from_customers = sum(
        (-t.net_position for t in open_transactions if t.net_position < 0), start=0
    )
    refunds_owed_to_customers = sum(
        (t.net_position for t in open_transactions if t.net_position > 0), start=0
    )

    low_stock_materials = Material.objects.filter(
        total_stock_count__gt=0, available_count__lte=F("total_stock_count") * 0.1
    ).order_by("available_count")[:10]

    recent_transactions = RentalTransaction.objects.select_related("customer").order_by("-date_out", "-id")[:10]

    context = {
        "cash_in": cash_in,
        "cash_out": cash_out,
        "deposits_held": deposits_held,
        "pending_from_customers": pending_from_customers,
        "refunds_owed_to_customers": refunds_owed_to_customers,
        "low_stock_materials": low_stock_materials,
        "recent_transactions": recent_transactions,
        "month_label": month_start.strftime("%B %Y"),
    }
    return render(request, "rentals/dashboard.html", context)
