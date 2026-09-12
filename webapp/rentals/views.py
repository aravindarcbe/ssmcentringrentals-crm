import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, F
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RentalTransactionForm, RentalLineItemFormSet
from .models import (
    Material,
    RentalTransaction,
    RentalLineItem,
    Receipt,
    Payment,
    DailyExpense,
    ProductPurchase,
    DepositLedger,
    StockMovement,
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


MANAGE_SECTIONS = [
    {
        "title": "Customers",
        "description": "Names, phone numbers, and addresses.",
        "links": [("Customers", "/admin/rentals/customer/")],
    },
    {
        "title": "Materials & Stock",
        "description": "What you rent out, and how much of it you have.",
        "links": [
            ("Materials", "/admin/rentals/material/"),
            ("Material categories", "/admin/rentals/materialcategory/"),
            ("Stock movements", "/admin/rentals/stockmovement/"),
        ],
    },
    {
        "title": "Rentals & Returns",
        "description": "Rent out material (bill on advance) and process returns (bill on return).",
        "links": [
            ("New rental", "/rentals/new/"),
            ("Rental transactions", "/admin/rentals/rentaltransaction/"),
        ],
    },
    {
        "title": "Money In",
        "description": "Payments received from customers against a rental.",
        "links": [("Receipts", "/admin/rentals/receipt/")],
    },
    {
        "title": "Money Out",
        "description": "Salary, loans, stock purchases, and day-to-day expenses.",
        "links": [
            ("Payments", "/admin/rentals/payment/"),
            ("Product purchases", "/admin/rentals/productpurchase/"),
            ("Daily expenses", "/admin/rentals/dailyexpense/"),
        ],
    },
]


@staff_member_required
def manage_home(request):
    return render(request, "rentals/manage.html", {"sections": MANAGE_SECTIONS})


def _generate_invoice_number():
    existing = RentalTransaction.objects.filter(invoice_number__regex=r"^SSM/INV/\d+$")
    max_n = 0
    for t in existing:
        m = re.match(r"^SSM/INV/(\d+)$", t.invoice_number)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"SSM/INV/{max_n + 1:04d}"


def _to_decimal(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _decrement_stock(material_id, count):
    """Reduce available_count by count, clamped at 0. Returns True if stock was insufficient."""
    material = Material.objects.get(pk=material_id)
    insufficient = count > material.available_count
    material.available_count = max(0, material.available_count - count)
    material.save(update_fields=["available_count"])
    return insufficient


@staff_member_required
def rental_new(request):
    if request.method == "POST":
        form = RentalTransactionForm(request.POST)
        formset = RentalLineItemFormSet(request.POST, queryset=RentalLineItem.objects.none(), prefix="items")
        if form.is_valid() and formset.is_valid():
            line_forms = [
                lf for lf in formset
                if lf.cleaned_data and not lf.cleaned_data.get("DELETE") and lf.cleaned_data.get("material")
            ]
            if not line_forms:
                messages.error(request, "Add at least one material line item.")
            else:
                transaction = form.save(commit=False)
                transaction.invoice_number = _generate_invoice_number()
                transaction.status = RentalTransaction.STATUS_OPEN
                transaction.save()

                stock_warnings = []
                for line_form in line_forms:
                    line = line_form.save(commit=False)
                    line.transaction = transaction
                    line.save()
                    StockMovement.objects.create(
                        material=line.material,
                        transaction=transaction,
                        direction=StockMovement.DIRECTION_OUT,
                        count=line.count,
                        date=transaction.date_out,
                    )
                    if _decrement_stock(line.material_id, line.count):
                        stock_warnings.append(str(line.material))

                deposit_amount = _to_decimal(request.POST.get("deposit_amount"))
                if deposit_amount > 0:
                    DepositLedger.objects.create(
                        transaction=transaction, date=transaction.date_out, amount_collected=deposit_amount
                    )

                if stock_warnings:
                    messages.warning(
                        request,
                        "Rented more than the recorded available stock for: " + ", ".join(stock_warnings)
                        + ". Available count set to 0 — update stock counts if this material's numbers are wrong.",
                    )

                messages.success(request, f"Rental {transaction.invoice_number} created.")
                return redirect("rentals:rental_detail", pk=transaction.pk)
    else:
        form = RentalTransactionForm(initial={"date_out": date.today()})
        formset = RentalLineItemFormSet(queryset=RentalLineItem.objects.none(), prefix="items")

    return render(request, "rentals/rental_form.html", {"form": form, "formset": formset})


@staff_member_required
def rental_detail(request, pk):
    transaction = get_object_or_404(
        RentalTransaction.objects.select_related("customer").prefetch_related(
            "line_items__material", "deposit_entries", "receipts"
        ),
        pk=pk,
    )
    return render(request, "rentals/rental_detail.html", {"t": transaction})


@staff_member_required
def rental_return(request, pk):
    transaction = get_object_or_404(RentalTransaction, pk=pk)
    line_items = list(transaction.line_items.select_related("material"))

    if request.method == "POST":
        any_change = False
        for item in line_items:
            count_key = f"return_count_{item.id}"
            date_key = f"return_date_{item.id}"
            if count_key not in request.POST:
                continue
            try:
                requested = int(request.POST.get(count_key) or 0)
            except ValueError:
                requested = item.count_returned
            new_returned = max(item.count_returned, min(requested, item.count))
            delta = new_returned - item.count_returned
            if delta > 0:
                item.count_returned = new_returned
                item.date_returned = request.POST.get(date_key) or date.today()
                item.save()
                StockMovement.objects.create(
                    material=item.material,
                    transaction=transaction,
                    direction=StockMovement.DIRECTION_IN,
                    count=delta,
                    date=item.date_returned,
                )
                Material.objects.filter(pk=item.material_id).update(available_count=F("available_count") + delta)
                any_change = True

        refund_amount = _to_decimal(request.POST.get("refund_amount"))
        if refund_amount > 0:
            DepositLedger.objects.create(
                transaction=transaction, date=date.today(), amount_refunded=refund_amount, note="Refund on return"
            )
            any_change = True

        extra_receipt_amount = _to_decimal(request.POST.get("extra_receipt_amount"))
        if extra_receipt_amount > 0:
            Receipt.objects.create(
                transaction=transaction,
                date=date.today(),
                amount=extra_receipt_amount,
                payment_mode="CASH",
                note="Balance settled on return",
            )
            any_change = True

        line_items = list(transaction.line_items.all())
        if all(li.is_fully_returned for li in line_items):
            transaction.status = RentalTransaction.STATUS_CLOSED
        elif any(li.count_returned > 0 for li in line_items):
            transaction.status = RentalTransaction.STATUS_PARTIALLY_RETURNED
        else:
            transaction.status = RentalTransaction.STATUS_OPEN
        transaction.save()

        if any_change:
            messages.success(request, "Return processed.")
        else:
            messages.info(request, "No changes submitted.")
        return redirect("rentals:rental_detail", pk=transaction.pk)

    return render(request, "rentals/rental_return.html", {"t": transaction, "line_items": line_items})
