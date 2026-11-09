"""Shared logic for importing the owner's Excel tracker format (customers,
rentals, receipts, payments, purchases, expenses) into the database.

Used by both `manage.py import_excel_data` (reads the checked-in reference
file at docs/source-data/) and the web upload page at /import-data/ (reads
whatever .xlsx a staff member uploads, in the same sheet layout).

See the notes at the top of management/commands/import_excel_data.py for
this import's known limitations — it's a best-effort import of a manually-
kept spreadsheet, not a lossless migration.
"""
import re
from datetime import date, datetime

from rentals.models import (
    Customer,
    MaterialCategory,
    Material,
    RentalTransaction,
    RentalLineItem,
    DepositLedger,
    Receipt,
    Payment,
    ProductPurchase,
    PurchaseBill,
    DailyExpense,
)


class ExcelImportError(Exception):
    """Raised when the uploaded workbook doesn't match the expected sheet layout."""


def normalize(name):
    return re.sub(r"\s+", "", (name or "").strip().lower())


def to_str_phone(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value))
    return str(value).strip()


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    if isinstance(value, str):
        parts = value.strip().split(".")
        if len(parts) == 3:
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return date(year, month, day)
            except ValueError:
                return None
    return None


def map_payment_mode(value):
    v = (value or "").strip().lower()
    if v == "cash":
        return "CASH"
    if v == "gpay":
        return "GPAY"
    if v == "card":
        return "CARD"
    return "BANK"


CATEGORY_KEYWORDS = [
    ("jockey", "Jockey"),
    ("sheet", "Sheet"),
    ("span", "Span"),
    ("runner", "Runner"),
]

REQUIRED_SHEETS = [
    "Client Details",
    "Invoice ",
    "Recepit",
    "Payment",
    "Product purchase",
    "Daily expense",
]


def guess_category(product_name):
    lower = (product_name or "").lower()
    for keyword, category_name in CATEGORY_KEYWORDS:
        if keyword in lower:
            return category_name
    return "Wood / Other"


def run_import(wb):
    """Run the import against an already-loaded openpyxl Workbook. Returns
    a dict of stats. Raises ExcelImportError if the workbook is missing a
    required sheet (e.g. the wrong file was uploaded)."""
    missing = [name for name in REQUIRED_SHEETS if name not in wb.sheetnames]
    if missing:
        raise ExcelImportError(
            f"This file doesn't look like the expected tracker format — missing sheet(s): {', '.join(missing)}. "
            f"Found sheets: {', '.join(wb.sheetnames)}."
        )

    stats = {}

    # ---------------------------------------------------------------
    # 1. Customers from "Client Details"
    # ---------------------------------------------------------------
    customers_by_key = {normalize(c.name): c for c in Customer.objects.all()}
    customer_seq = Customer.objects.filter(customer_id__startswith="SSM-CUS-IMPORT-").count()

    def next_customer_id():
        nonlocal customer_seq
        customer_seq += 1
        return f"SSM-CUS-IMPORT-{customer_seq:04d}"

    ws = wb["Client Details"]
    created_customers = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        name, phone, place, aadhar = (row + (None,) * 4)[:4]
        if not name:
            continue
        key = normalize(name)
        if key in customers_by_key:
            continue
        customer = Customer.objects.create(
            customer_id=next_customer_id(),
            name=name.strip(),
            phone=to_str_phone(phone),
            place=(place or "").strip() if isinstance(place, str) else "",
            aadhar_number=to_str_phone(aadhar),
        )
        customers_by_key[key] = customer
        created_customers += 1
    stats["customers_created"] = created_customers

    def get_or_create_customer(name, phone=None):
        key = normalize(name)
        if key in customers_by_key:
            return customers_by_key[key]
        customer = Customer.objects.create(customer_id=next_customer_id(), name=name.strip(), phone=to_str_phone(phone))
        customers_by_key[key] = customer
        return customer

    # ---------------------------------------------------------------
    # 2. Materials cache (created lazily as Invoice/Product purchase rows are read)
    # ---------------------------------------------------------------
    materials_by_label = {m.size_label: m for m in Material.objects.all()}
    categories_by_name = {c.name: c for c in MaterialCategory.objects.all()}

    def get_or_create_category(name):
        if name not in categories_by_name:
            categories_by_name[name] = MaterialCategory.objects.create(name=name)
        return categories_by_name[name]

    def get_or_create_material(product_name, total_ft, count, rate):
        label = (product_name or "Unspecified").strip()
        if label in materials_by_label:
            return materials_by_label[label]
        per_unit_ft = (total_ft / count) if (total_ft and count) else (total_ft or 1)
        material = Material.objects.create(
            category=get_or_create_category(guess_category(label)),
            size_label=label,
            ft_value=per_unit_ft,
            default_rate_per_day=rate or 0,
            total_stock_count=0,
            available_count=0,
        )
        materials_by_label[label] = material
        return material

    # ---------------------------------------------------------------
    # 3. Rental transactions + line items + deposits from "Invoice"
    # ---------------------------------------------------------------
    ws = wb["Invoice "]
    counters = {"transactions": 0, "line_items": 0}
    invoice_seq = RentalTransaction.objects.filter(invoice_number__startswith="SSM/INV/IMPORT-").count()

    def flush_transaction(block):
        nonlocal invoice_seq
        if block is None or not block["line_items"]:
            return
        invoice_seq += 1
        customer = get_or_create_customer(block["customer_name"], block["phone"])
        is_closed = (block["reminder"] or "").strip().lower() == "completed"
        remarks_parts = [p for p in [block["reminder"], block["remarks"]] if p]
        transaction = RentalTransaction.objects.create(
            invoice_number=f"SSM/INV/IMPORT-{invoice_seq:04d}",
            customer=customer,
            date_out=block["date_out"] or date.today(),
            status=RentalTransaction.STATUS_CLOSED if is_closed else RentalTransaction.STATUS_OPEN,
            discount=block["discount_sum"],
            remarks=" / ".join(str(p) for p in remarks_parts)[:255],
        )
        counters["transactions"] += 1
        for item in block["line_items"]:
            material = get_or_create_material(item["product"], item["ft"], item["count"], item["rate"])
            RentalLineItem.objects.create(
                transaction=transaction,
                material=material,
                count=int(item["count"] or 1),
                days_estimated=int(item["days"] or 1),
                rate=item["rate"] or 0,
                count_returned=int(item["count"] or 1) if is_closed else 0,
            )
            counters["line_items"] += 1
        if block["deposit_sum"]:
            DepositLedger.objects.create(
                transaction=transaction, date=block["date_out"] or date.today(), amount_collected=block["deposit_sum"]
            )

    current = None
    for row in ws.iter_rows(min_row=3, values_only=True):
        row = (row + (None,) * 15)[:15]
        date_val, client, phone, product, count, ft, days, rate, bill, paid, pending, discount, deposit, reminder, remarks = row

        if client:
            flush_transaction(current)
            current = dict(
                date_out=parse_date(date_val),
                customer_name=client,
                phone=phone,
                discount_sum=0,
                deposit_sum=0,
                reminder=reminder,
                remarks=remarks,
                line_items=[],
            )
            if product:
                current["line_items"].append(dict(product=product, count=count, ft=ft, days=days, rate=rate))
            if discount:
                current["discount_sum"] += discount
            if deposit:
                current["deposit_sum"] += deposit
        elif product and current is not None:
            current["line_items"].append(dict(product=product, count=count, ft=ft, days=days, rate=rate))
            if discount:
                current["discount_sum"] += discount
            if deposit:
                current["deposit_sum"] += deposit

    flush_transaction(current)
    stats["transactions_created"] = counters["transactions"]
    stats["line_items_created"] = counters["line_items"]

    # ---------------------------------------------------------------
    # 4. Receipts from "Recepit" (best-effort match to a transaction, see notes)
    # ---------------------------------------------------------------
    ws = wb["Recepit"]
    receipts_created = 0
    receipts_skipped = 0
    for row in ws.iter_rows(min_row=7, values_only=True):
        row = (row + (None,) * 6)[:6]
        date_val, invoice_no, client, amount, mode, balance_deposit = row
        if not client or amount is None:
            continue
        receipt_date = parse_date(date_val)
        key = normalize(client)
        customer = customers_by_key.get(key)
        transaction = None
        if customer:
            candidates = RentalTransaction.objects.filter(customer=customer).order_by("-date_out")
            if receipt_date:
                earlier = [t for t in candidates if t.date_out <= receipt_date]
                transaction = earlier[0] if earlier else (candidates.first() if candidates.exists() else None)
            else:
                transaction = candidates.first()
        if transaction is None:
            receipts_skipped += 1
            continue
        Receipt.objects.create(
            transaction=transaction,
            date=receipt_date or transaction.date_out,
            amount=amount,
            payment_mode=map_payment_mode(mode),
            note=f"Sheet invoice no: {invoice_no}" if invoice_no else "",
        )
        receipts_created += 1
    stats["receipts_created"] = receipts_created
    stats["receipts_skipped_unmatched"] = receipts_skipped

    # ---------------------------------------------------------------
    # 5. Outgoing payments from "Payment"
    # ---------------------------------------------------------------
    ws = wb["Payment"]
    payments_created = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        row = (row + (None,) * 5)[:5]
        date_val, description, payee, amount, mode = row
        parsed_date = parse_date(date_val)
        if not parsed_date or amount is None:
            continue
        Payment.objects.create(
            date=parsed_date,
            description=(description or "").strip(),
            payee=(payee or "").strip() if isinstance(payee, str) else "",
            amount=amount,
            payment_mode=map_payment_mode(mode),
        )
        payments_created += 1
    stats["payments_created"] = payments_created

    # ---------------------------------------------------------------
    # 6. Stock buy-ins from "Product purchase"
    # ---------------------------------------------------------------
    ws = wb["Product purchase"]
    purchases_created = 0
    bill_seq = PurchaseBill.objects.filter(bill_number__startswith="SSM/PUR/IMPORT-").count()
    for row in ws.iter_rows(min_row=5, values_only=True):
        row = (row + (None,) * 6)[:6]
        date_val, category, size, count, rate, amount = row
        parsed_date = parse_date(date_val)
        if not parsed_date or not category or count is None:
            continue
        computed_amount = amount if amount is not None else ((count * rate) if rate else 0)
        bill_seq += 1
        # The source sheet has no bill-grouping column (one row per line item),
        # so each imported row becomes its own single-line bill.
        bill = PurchaseBill.objects.create(
            bill_number=f"SSM/PUR/IMPORT-{bill_seq:04d}",
            date=parsed_date,
            remarks="Imported from the owner's Excel tracker.",
        )
        ProductPurchase.objects.create(
            bill=bill,
            date=parsed_date,
            category=get_or_create_category(category.strip()),
            size_label=(size or "").strip() if isinstance(size, str) else "",
            count=int(count),
            rate=rate,
            amount=computed_amount,
        )
        purchases_created += 1
    stats["purchases_created"] = purchases_created

    # ---------------------------------------------------------------
    # 7. Daily expenses from "Daily expense"
    # ---------------------------------------------------------------
    ws = wb["Daily expense"]
    expenses_created = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        row = (row + (None,) * 5)[:5]
        date_val, category, description, amount, mode = row
        parsed_date = parse_date(date_val)
        if not parsed_date or amount is None:
            continue
        DailyExpense.objects.create(
            date=parsed_date,
            category=(category or "").strip() if isinstance(category, str) else "Uncategorized",
            description=(description or "").strip() if isinstance(description, str) else "",
            amount=amount,
            payment_mode=map_payment_mode(mode),
        )
        expenses_created += 1
    stats["expenses_created"] = expenses_created

    return stats
