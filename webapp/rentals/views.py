import re
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import partial

import openpyxl
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required as _staff_member_required
from django.db import transaction
from django.db.models import Sum, F, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .excel_import import run_import, ExcelImportError
from .purchase_pdf_import import parse_purchase_pdf
from .exports import ExportXLSXMixin
from .forms import (
    RentalTransactionForm,
    RentalLineItemFormSet,
    CustomerForm,
    MaterialForm,
    MaterialCategoryForm,
    ReceiptForm,
    PaymentForm,
    ProductPurchaseForm,
    PurchaseBillForm,
    ProductPurchaseLineItemFormSet,
    DailyExpenseForm,
    ExcelUploadForm,
)
from .models import (
    Customer,
    Material,
    MaterialCategory,
    RentalTransaction,
    RentalLineItem,
    Receipt,
    Payment,
    DailyExpense,
    ProductPurchase,
    PurchaseBill,
    DepositLedger,
    StockMovement,
)

# staff_member_required's login_url defaults to the hardcoded "admin:login", unlike
# login_required which reads settings.LOGIN_URL — without this override every
# @staff_member_required view below would bounce to Django admin's default login
# page instead of our branded rentals:login.
staff_member_required = partial(_staff_member_required, login_url="rentals:login")


@staff_member_required
def dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)

    cash_in = Receipt.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0

    payments_out = Payment.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    expenses_out = DailyExpense.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    purchases_out = ProductPurchase.objects.filter(date__gte=month_start).aggregate(total=Sum("amount"))["total"] or 0
    cash_out = payments_out + expenses_out + purchases_out

    receipts_today = Receipt.objects.filter(date=today).aggregate(total=Sum("amount"))["total"] or 0
    receipts_month = cash_in
    payments_today = Payment.objects.filter(date=today).aggregate(total=Sum("amount"))["total"] or 0
    payments_month = payments_out

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

    # Material due back this month: due_date is computed (date_out + days_estimated),
    # not stored, so filter in Python rather than at the DB level — the open-line-item
    # set is small for this business, so this stays cheap.
    open_lines = (
        RentalLineItem.objects.exclude(transaction__status=RentalTransaction.STATUS_CLOSED)
        .exclude(count_returned=F("count"))
        .select_related("transaction__customer", "material")
    )
    due_this_month = sorted(
        (
            line for line in open_lines
            if line.due_date.year == today.year and line.due_date.month == today.month
        ),
        key=lambda line: line.due_date,
    )

    context = {
        "cash_in": cash_in,
        "cash_out": cash_out,
        "receipts_today": receipts_today,
        "receipts_month": receipts_month,
        "payments_today": payments_today,
        "payments_month": payments_month,
        "deposits_held": deposits_held,
        "pending_from_customers": pending_from_customers,
        "refunds_owed_to_customers": refunds_owed_to_customers,
        "due_this_month": due_this_month,
        "today": today,
        "low_stock_materials": low_stock_materials,
        "recent_transactions": recent_transactions,
        "month_label": month_start.strftime("%B %Y"),
    }
    return render(request, "rentals/dashboard.html", context)


MANAGE_SECTIONS = [
    {
        "title": "Customers",
        "description": "Names, phone numbers, and addresses.",
        "links": [("Customers", "/customers/")],
    },
    {
        "title": "Materials & Stock",
        "description": "What you rent out, and how much of it you have.",
        "links": [
            ("Materials", "/materials/"),
            ("Material categories", "/categories/"),
            ("Stock movements", "/stock-movements/"),
        ],
    },
    {
        "title": "Rentals & Returns",
        "description": "Rent out material (bill on advance) and process returns (bill on return).",
        "links": [
            ("New rental", "/rentals/new/"),
            ("Rental transactions", "/rental-transactions/"),
        ],
    },
    {
        "title": "Money In",
        "description": "Payments received from customers against a rental.",
        "links": [("Receipts", "/receipts/")],
    },
    {
        "title": "Money Out",
        "description": "Salary, loans, stock purchases, and day-to-day expenses.",
        "links": [
            ("Payments", "/payments/"),
            ("Product purchases", "/purchases/"),
            ("Daily expenses", "/expenses/"),
        ],
    },
    {
        "title": "Data",
        "description": "Bring in real data from the owner's Excel tracker.",
        "links": [("Import Data", "/import-data/")],
    },
    {
        "title": "Reports",
        "description": "Pending amounts, deposits held, monthly cash flow, expense breakdown.",
        "links": [("Reports", "/reports/")],
    },
]


@staff_member_required
def manage_home(request):
    return render(request, "rentals/manage.html", {"sections": MANAGE_SECTIONS})


@staff_member_required
def reports_view(request):
    today = date.today()

    # Pending amounts / refunds owed, by customer — open transactions only.
    pending_by_customer = {}
    refund_by_customer = {}
    for t in RentalTransaction.objects.exclude(status=RentalTransaction.STATUS_CLOSED).select_related("customer"):
        pos = t.net_position
        if pos < 0:
            pending_by_customer[t.customer] = pending_by_customer.get(t.customer, 0) + (-pos)
        elif pos > 0:
            refund_by_customer[t.customer] = refund_by_customer.get(t.customer, 0) + pos
    pending_rows = sorted(
        ({"customer": c, "amount": a} for c, a in pending_by_customer.items()),
        key=lambda r: r["amount"], reverse=True,
    )
    refund_rows = sorted(
        ({"customer": c, "amount": a} for c, a in refund_by_customer.items()),
        key=lambda r: r["amount"], reverse=True,
    )

    # Deposits held, by customer — across all their transactions, not just open ones.
    deposits_by_customer = {}
    for t in RentalTransaction.objects.select_related("customer").prefetch_related("deposit_entries"):
        held = t.deposit_held
        if held:
            deposits_by_customer[t.customer] = deposits_by_customer.get(t.customer, 0) + held
    deposit_rows = sorted(
        ({"customer": c, "amount": a} for c, a in deposits_by_customer.items() if a),
        key=lambda r: r["amount"], reverse=True,
    )

    # Monthly cash flow, last 12 months.
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()

    monthly_rows = []
    for y, m in months:
        month_start = date(y, m, 1)
        next_month = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        cash_in = Receipt.objects.filter(date__gte=month_start, date__lt=next_month).aggregate(total=Sum("amount"))["total"] or 0
        payments_out = Payment.objects.filter(date__gte=month_start, date__lt=next_month).aggregate(total=Sum("amount"))["total"] or 0
        purchases_out = ProductPurchase.objects.filter(date__gte=month_start, date__lt=next_month).aggregate(total=Sum("amount"))["total"] or 0
        expenses_out = DailyExpense.objects.filter(date__gte=month_start, date__lt=next_month).aggregate(total=Sum("amount"))["total"] or 0
        cash_out = payments_out + purchases_out + expenses_out
        monthly_rows.append({
            "label": month_start.strftime("%b %Y"),
            "cash_in": cash_in,
            "cash_out": cash_out,
            "net": cash_in - cash_out,
        })

    expense_breakdown = DailyExpense.objects.values("category").annotate(total=Sum("amount")).order_by("-total")

    context = {
        "pending_rows": pending_rows,
        "refund_rows": refund_rows,
        "deposit_rows": deposit_rows,
        "monthly_rows": monthly_rows,
        "expense_breakdown": expense_breakdown,
    }
    return render(request, "rentals/reports.html", context)


@staff_member_required
def excel_import_view(request):
    stats = None
    if request.method == "POST":
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                wb = openpyxl.load_workbook(form.cleaned_data["file"], data_only=True)
                with transaction.atomic():
                    stats = run_import(wb)
                messages.success(request, "Import complete — see the results below.")
            except ExcelImportError as e:
                messages.error(request, str(e))
            except Exception:
                messages.error(
                    request,
                    "Couldn't read that file — make sure it's a valid, unprotected .xlsx workbook "
                    "in the same format as the owner's tracker (Client Details, Invoice, Recepit, "
                    "Payment, Product purchase, Daily expense sheets).",
                )
    else:
        form = ExcelUploadForm()
    return render(request, "rentals/excel_import.html", {"form": form, "stats": stats})


# Business data only, in FK-safe delete order — never touches User/Group accounts,
# so existing logins (dev, admin, etc.) keep working after a reset.
_DANGER_RESET_MODELS = [
    StockMovement,
    DepositLedger,
    Receipt,
    RentalLineItem,
    RentalTransaction,
    Payment,
    ProductPurchase,
    PurchaseBill,
    DailyExpense,
    Material,
    MaterialCategory,
    Customer,
]


@staff_member_required
def danger_reset_data_view(request):
    if not request.user.is_superuser:
        messages.error(request, "Only a superuser account can delete all data.")
        return redirect("rentals:excel_import")
    if request.method != "POST":
        return redirect("rentals:excel_import")

    with transaction.atomic():
        counts = {}
        for model in _DANGER_RESET_MODELS:
            counts[model.__name__] = model.objects.count()
            model.objects.all().delete()

    messages.success(
        request,
        "All business data deleted: " + ", ".join(f"{k} ({v})" for k, v in counts.items() if v),
    )
    return redirect("rentals:excel_import")


def _generate_invoice_number():
    existing = RentalTransaction.objects.filter(invoice_number__regex=r"^SSM/INV/\d+$")
    max_n = 0
    for t in existing:
        m = re.match(r"^SSM/INV/(\d+)$", t.invoice_number)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"SSM/INV/{max_n + 1:04d}"


def _generate_bill_number():
    existing = PurchaseBill.objects.filter(bill_number__regex=r"^SSM/PUR/\d+$")
    max_n = 0
    for b in existing:
        m = re.match(r"^SSM/PUR/(\d+)$", b.bill_number)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"SSM/PUR/{max_n + 1:04d}"


def _generate_customer_id():
    existing = Customer.objects.filter(customer_id__regex=r"^SSM-CUS-\d+$")
    max_n = 0
    for c in existing:
        m = re.match(r"^SSM-CUS-(\d+)$", c.customer_id)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"SSM-CUS-{max_n + 1:04d}"


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


def _whatsapp_invoice_url(t):
    """wa.me deep link pre-filled with an invoice summary. India-only phone
    normalization (10-digit local numbers get a 91 prefix), matching the
    business this app serves — not meant to generalize beyond that."""
    from urllib.parse import quote

    digits = re.sub(r"\D", "", t.customer.phone or "")
    if len(digits) == 10:
        digits = "91" + digits
    message = (
        f"Hello {t.customer.name}, here is your invoice from Sri Sai Murugan Centring Rentals.\n"
        f"Invoice No: {t.invoice_number}\n"
        f"Date: {t.date_out.strftime('%d/%m/%Y')}\n"
        f"Grand Total: Rs. {t.grand_total:,.2f}\n"
        f"Thank you for your business!"
    )
    return f"https://wa.me/{digits}?text={quote(message)}"


@staff_member_required
def rental_invoice(request, pk):
    transaction = get_object_or_404(
        RentalTransaction.objects.select_related("customer").prefetch_related("line_items__material"),
        pk=pk,
    )
    if request.method == "POST":
        transaction.transportation = _to_decimal(request.POST.get("transportation"))
        transaction.damage_charge = _to_decimal(request.POST.get("damage_charge"))
        transaction.save(update_fields=["transportation", "damage_charge"])
        messages.success(request, "Invoice charges updated.")
        return redirect("rentals:rental_invoice", pk=transaction.pk)
    return render(request, "rentals/invoice.html", {"t": transaction, "whatsapp_url": _whatsapp_invoice_url(transaction)})


@staff_member_required
def customer_statement(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    transactions = (
        RentalTransaction.objects.filter(customer=customer)
        .prefetch_related("line_items", "deposit_entries", "receipts")
        .order_by("-date_out", "-id")
    )

    total_billed = sum((t.total_bill_amount for t in transactions), start=0)
    total_received = sum((t.total_received for t in transactions), start=0)
    total_deposits_held = sum((t.deposit_held for t in transactions), start=0)
    net_balance = sum((t.net_position for t in transactions), start=0)

    context = {
        "customer": customer,
        "transactions": transactions,
        "total_billed": total_billed,
        "total_received": total_received,
        "total_deposits_held": total_deposits_held,
        "net_balance": net_balance,
    }
    return render(request, "rentals/customer_statement.html", context)


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


@staff_member_required
def global_search(request):
    query = (request.GET.get("q") or "").strip()
    customers = Customer.objects.none()
    transactions = RentalTransaction.objects.none()
    materials = Material.objects.none()
    if query:
        customers = Customer.objects.filter(name__icontains=query) | Customer.objects.filter(phone__icontains=query)
        transactions = RentalTransaction.objects.select_related("customer").filter(
            invoice_number__icontains=query
        ) | RentalTransaction.objects.select_related("customer").filter(customer__name__icontains=query)
        materials = Material.objects.select_related("category").filter(size_label__icontains=query)
    return render(
        request,
        "rentals/search_results.html",
        {"query": query, "customers": customers[:20], "transactions": transactions.distinct()[:20], "materials": materials[:20]},
    )


# ---------------------------------------------------------------------------
# Custom CRUD screens for Customers, Materials, Receipts, Payments, Product
# Purchases, and Daily Expenses — previously only available via /admin/.
# Two small shared mixins (not a full abstraction, just the identical htmx
# wiring described in the plan) so each model's views stay a few lines each.
# ---------------------------------------------------------------------------


class HtmxRowsMixin:
    """ListViews: an htmx search request re-renders only the rows partial."""

    rows_template_name = None

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return [self.rows_template_name]
        return [self.template_name]


class HtmxDeleteMixin:
    """DeleteViews: POST-only, no confirm page — htmx removes the row in place.

    Overrides post() directly rather than delete(): Django's BaseDeleteView.post()
    (since the Form-based rewrite in Django 4.0) goes through get_form()/form_valid()
    and never calls self.delete() at all, so overriding delete() alone is silently
    ignored — confirmed by testing, not assumed.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        if request.headers.get("HX-Request") == "true":
            return HttpResponse(status=200)
        return redirect(self.success_url)


@method_decorator(staff_member_required, name="dispatch")
class CustomerListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    model = Customer
    template_name = "rentals/customer_list.html"
    rows_template_name = "rentals/_customer_rows.html"
    context_object_name = "customers"
    paginate_by = 25
    export_filename = "customers"
    export_columns = [
        ("Customer ID", "customer_id"),
        ("Name", "name"),
        ("Phone", "phone"),
        ("Type", lambda c: c.get_customer_type_display()),
        ("Place", "place"),
        ("Address", "address"),
        ("Pincode", "pincode"),
        ("Construction Site Address", "construction_site_address"),
        ("Payment Terms", "payment_terms"),
        ("Aadhar Number", "aadhar_number"),
    ]

    def get_queryset(self):
        qs = Customer.objects.annotate(
            open_count=Count(
                "rental_transactions",
                filter=~Q(rental_transactions__status=RentalTransaction.STATUS_CLOSED),
            )
        )
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = (
                qs.filter(name__icontains=query)
                | qs.filter(phone__icontains=query)
                | qs.filter(place__icontains=query)
                | qs.filter(customer_id__icontains=query)
            )
        return qs


@method_decorator(staff_member_required, name="dispatch")
class CustomerCreateView(CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "rentals/customer_form.html"
    success_url = reverse_lazy("rentals:customer_list")

    def form_valid(self, form):
        form.instance.customer_id = _generate_customer_id()
        return super().form_valid(form)


@method_decorator(staff_member_required, name="dispatch")
class CustomerUpdateView(UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "rentals/customer_form.html"
    success_url = reverse_lazy("rentals:customer_list")


@method_decorator(staff_member_required, name="dispatch")
class CustomerDeleteView(HtmxDeleteMixin, DeleteView):
    model = Customer
    success_url = reverse_lazy("rentals:customer_list")


@method_decorator(staff_member_required, name="dispatch")
class MaterialListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    model = Material
    template_name = "rentals/material_list.html"
    rows_template_name = "rentals/_material_rows.html"
    context_object_name = "materials"
    paginate_by = 25
    export_filename = "materials"
    export_columns = [
        ("Category", lambda m: m.category.name),
        ("Size", "size_label"),
        ("Rate", "default_rate_per_day"),
        ("Rate Unit", lambda m: m.get_rate_unit_display()),
        ("Available", "available_count"),
        ("Total Stock", "total_stock_count"),
    ]

    def get_queryset(self):
        qs = Material.objects.select_related("category")
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(size_label__icontains=query) | qs.filter(category__name__icontains=query)
        return qs


@method_decorator(staff_member_required, name="dispatch")
class MaterialCreateView(CreateView):
    model = Material
    form_class = MaterialForm
    template_name = "rentals/material_form.html"
    success_url = reverse_lazy("rentals:material_list")


@method_decorator(staff_member_required, name="dispatch")
class MaterialUpdateView(UpdateView):
    model = Material
    form_class = MaterialForm
    template_name = "rentals/material_form.html"
    success_url = reverse_lazy("rentals:material_list")


@method_decorator(staff_member_required, name="dispatch")
class MaterialDeleteView(HtmxDeleteMixin, DeleteView):
    model = Material
    success_url = reverse_lazy("rentals:material_list")


@method_decorator(staff_member_required, name="dispatch")
class ReceiptListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    model = Receipt
    template_name = "rentals/receipt_list.html"
    rows_template_name = "rentals/_receipt_rows.html"
    context_object_name = "receipts"
    paginate_by = 25
    export_filename = "receipts"
    export_columns = [
        ("Date", "date"),
        ("Invoice", lambda r: r.transaction.invoice_number),
        ("Customer", lambda r: r.transaction.customer.name),
        ("Amount", "amount"),
        ("Mode", lambda r: r.get_payment_mode_display()),
        ("Note", "note"),
    ]

    def get_queryset(self):
        qs = Receipt.objects.select_related("transaction", "transaction__customer")
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(transaction__invoice_number__icontains=query) | qs.filter(
                transaction__customer__name__icontains=query
            )
        return qs


@method_decorator(staff_member_required, name="dispatch")
class ReceiptCreateView(CreateView):
    model = Receipt
    form_class = ReceiptForm
    template_name = "rentals/receipt_form.html"
    success_url = reverse_lazy("rentals:receipt_list")


@method_decorator(staff_member_required, name="dispatch")
class ReceiptUpdateView(UpdateView):
    model = Receipt
    form_class = ReceiptForm
    template_name = "rentals/receipt_form.html"
    success_url = reverse_lazy("rentals:receipt_list")


@method_decorator(staff_member_required, name="dispatch")
class ReceiptDeleteView(HtmxDeleteMixin, DeleteView):
    model = Receipt
    success_url = reverse_lazy("rentals:receipt_list")


@method_decorator(staff_member_required, name="dispatch")
class PaymentListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    model = Payment
    template_name = "rentals/payment_list.html"
    rows_template_name = "rentals/_payment_rows.html"
    context_object_name = "payments"
    paginate_by = 25
    export_filename = "payments"
    export_columns = [
        ("Date", "date"),
        ("Description", "description"),
        ("Payee", "payee"),
        ("Amount", "amount"),
        ("Mode", lambda p: p.get_payment_mode_display()),
    ]

    def get_queryset(self):
        qs = Payment.objects.all()
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(description__icontains=query) | qs.filter(payee__icontains=query)
        return qs


@method_decorator(staff_member_required, name="dispatch")
class PaymentCreateView(CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = "rentals/payment_form.html"
    success_url = reverse_lazy("rentals:payment_list")


@method_decorator(staff_member_required, name="dispatch")
class PaymentUpdateView(UpdateView):
    model = Payment
    form_class = PaymentForm
    template_name = "rentals/payment_form.html"
    success_url = reverse_lazy("rentals:payment_list")


@method_decorator(staff_member_required, name="dispatch")
class PaymentDeleteView(HtmxDeleteMixin, DeleteView):
    model = Payment
    success_url = reverse_lazy("rentals:payment_list")


@staff_member_required
def purchase_bill_new(request):
    if request.method == "POST":
        form = PurchaseBillForm(request.POST)
        formset = ProductPurchaseLineItemFormSet(request.POST, queryset=ProductPurchase.objects.none(), prefix="items")
        if form.is_valid() and formset.is_valid():
            line_forms = [
                lf for lf in formset
                if lf.cleaned_data and not lf.cleaned_data.get("DELETE") and lf.cleaned_data.get("category")
            ]
            if not line_forms:
                messages.error(request, "Add at least one line item.")
            else:
                bill = form.save(commit=False)
                bill.bill_number = _generate_bill_number()
                bill.save()

                for line_form in line_forms:
                    line = line_form.save(commit=False)
                    line.bill = bill
                    line.date = bill.date
                    line.save()

                messages.success(request, f"Purchase bill {bill.bill_number} saved with {len(line_forms)} item(s).")
                return redirect("rentals:purchase_list")
    else:
        form = PurchaseBillForm(initial={"date": date.today()})
        formset = ProductPurchaseLineItemFormSet(queryset=ProductPurchase.objects.none(), prefix="items")

    return render(request, "rentals/purchase_bill_form.html", {
        "form": form,
        "formset": formset,
        "categories": MaterialCategory.objects.all(),
    })


@staff_member_required
@require_POST
def purchase_pdf_parse_view(request):
    """AJAX endpoint: best-effort text extraction from an uploaded vendor PDF bill
    (see purchase_pdf_import.py). Always 200s with whatever it could find — the
    caller shows the result in an editable review popup, never saves it directly."""
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "No file uploaded."}, status=400)
    try:
        result = parse_purchase_pdf(uploaded)
    except Exception:
        return JsonResponse(
            {"error": "Couldn't read that PDF — make sure it's a valid, unprotected .pdf file."}, status=400
        )
    return JsonResponse(result)


@method_decorator(staff_member_required, name="dispatch")
class ProductPurchaseListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    model = ProductPurchase
    template_name = "rentals/purchase_list.html"
    rows_template_name = "rentals/_purchase_rows.html"
    context_object_name = "purchases"
    paginate_by = 25
    export_filename = "purchases"
    export_columns = [
        ("Date", "date"),
        ("Bill Number", lambda p: p.bill.bill_number),
        ("Vendor", lambda p: p.bill.vendor_name),
        ("Category", lambda p: p.category.name),
        ("Size / Notes", lambda p: p.size_label or p.description),
        ("Count", "count"),
        ("Rate", "rate"),
        ("Amount", "amount"),
    ]

    def get_queryset(self):
        qs = ProductPurchase.objects.select_related("category", "bill")
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = (
                qs.filter(category__name__icontains=query)
                | qs.filter(size_label__icontains=query)
                | qs.filter(description__icontains=query)
                | qs.filter(bill__bill_number__icontains=query)
                | qs.filter(bill__vendor_name__icontains=query)
            )
        return qs


@method_decorator(staff_member_required, name="dispatch")
class ProductPurchaseUpdateView(UpdateView):
    model = ProductPurchase
    form_class = ProductPurchaseForm
    template_name = "rentals/purchase_form.html"
    success_url = reverse_lazy("rentals:purchase_list")


@method_decorator(staff_member_required, name="dispatch")
class ProductPurchaseDeleteView(HtmxDeleteMixin, DeleteView):
    model = ProductPurchase
    success_url = reverse_lazy("rentals:purchase_list")


@method_decorator(staff_member_required, name="dispatch")
class DailyExpenseListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    model = DailyExpense
    template_name = "rentals/expense_list.html"
    rows_template_name = "rentals/_expense_rows.html"
    context_object_name = "expenses"
    paginate_by = 25
    export_filename = "expenses"
    export_columns = [
        ("Date", "date"),
        ("Category", "category"),
        ("Description", "description"),
        ("Amount", "amount"),
        ("Mode", lambda e: e.get_payment_mode_display()),
    ]

    def get_queryset(self):
        qs = DailyExpense.objects.all()
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(category__icontains=query) | qs.filter(description__icontains=query)
        return qs


@method_decorator(staff_member_required, name="dispatch")
class DailyExpenseCreateView(CreateView):
    model = DailyExpense
    form_class = DailyExpenseForm
    template_name = "rentals/expense_form.html"
    success_url = reverse_lazy("rentals:expense_list")


@method_decorator(staff_member_required, name="dispatch")
class DailyExpenseUpdateView(UpdateView):
    model = DailyExpense
    form_class = DailyExpenseForm
    template_name = "rentals/expense_form.html"
    success_url = reverse_lazy("rentals:expense_list")


@method_decorator(staff_member_required, name="dispatch")
class DailyExpenseDeleteView(HtmxDeleteMixin, DeleteView):
    model = DailyExpense
    success_url = reverse_lazy("rentals:expense_list")


@method_decorator(staff_member_required, name="dispatch")
class MaterialCategoryListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    model = MaterialCategory
    template_name = "rentals/category_list.html"
    rows_template_name = "rentals/_category_rows.html"
    context_object_name = "categories"
    paginate_by = 25
    export_filename = "categories"
    export_columns = [("Name", "name")]

    def get_queryset(self):
        qs = MaterialCategory.objects.all()
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(name__icontains=query)
        return qs


@method_decorator(staff_member_required, name="dispatch")
class MaterialCategoryCreateView(CreateView):
    model = MaterialCategory
    form_class = MaterialCategoryForm
    template_name = "rentals/category_form.html"
    success_url = reverse_lazy("rentals:category_list")


@method_decorator(staff_member_required, name="dispatch")
class MaterialCategoryUpdateView(UpdateView):
    model = MaterialCategory
    form_class = MaterialCategoryForm
    template_name = "rentals/category_form.html"
    success_url = reverse_lazy("rentals:category_list")


@method_decorator(staff_member_required, name="dispatch")
class MaterialCategoryDeleteView(HtmxDeleteMixin, DeleteView):
    model = MaterialCategory
    success_url = reverse_lazy("rentals:category_list")


@method_decorator(staff_member_required, name="dispatch")
class StockMovementListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    """Read-only: stock movements are an audit trail driven by the rental
    workflow (New Rental / Process Return), not something staff hand-enter —
    matches how this data has always been produced, just without the raw
    admin UI."""

    model = StockMovement
    template_name = "rentals/stockmovement_list.html"
    rows_template_name = "rentals/_stockmovement_rows.html"
    context_object_name = "movements"
    paginate_by = 25
    export_filename = "stock_movements"
    export_columns = [
        ("Date", "date"),
        ("Material", lambda m: str(m.material)),
        ("Direction", lambda m: m.get_direction_display()),
        ("Count", "count"),
        ("Invoice", lambda m: m.transaction.invoice_number),
    ]

    def get_queryset(self):
        qs = StockMovement.objects.select_related("material", "material__category", "transaction")
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(material__size_label__icontains=query) | qs.filter(
                transaction__invoice_number__icontains=query
            )
        return qs


@method_decorator(staff_member_required, name="dispatch")
class RentalTransactionListView(ExportXLSXMixin, HtmxRowsMixin, ListView):
    """Read-only list: mutations happen via the existing New Rental / Rental
    Detail / Process Return screens, not a generic edit form — a transaction's
    line items, deposits, and receipts are too interlinked for a flat CRUD
    form to make sense."""

    model = RentalTransaction
    template_name = "rentals/rentaltransaction_list.html"
    rows_template_name = "rentals/_rentaltransaction_rows.html"
    context_object_name = "transactions"
    paginate_by = 25
    export_filename = "rental_transactions"
    export_columns = [
        ("Invoice", "invoice_number"),
        ("Customer", lambda t: t.customer.name),
        ("Date Out", "date_out"),
        ("Status", lambda t: t.get_status_display()),
        ("Total Bill", lambda t: t.total_bill_amount),
        ("Net Position", lambda t: t.net_position),
    ]

    def get_queryset(self):
        qs = RentalTransaction.objects.select_related("customer")
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(invoice_number__icontains=query) | qs.filter(customer__name__icontains=query)
        return qs
