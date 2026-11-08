"""Import the owner's real data from docs/source-data/SSMSALES_and_EXPENSES.xlsx
into the database, so the app can be explored with real records instead of
made-up demo data.

Run with: python manage.py import_excel_data

For the same import via a browser upload instead of this fixed checked-in
file, see the "Import Data" page (rentals:excel_import), which shares the
exact same logic in rentals/excel_import.py.

Notes / limitations (the source sheet is a manual, inconsistently-filled
spreadsheet, so this is best-effort, not a lossless migration):
  - The "Invoice" sheet has no invoice-number column, so transaction invoice
    numbers are auto-generated as SSM/INV/IMPORT-####.
  - The "Recepit" sheet's "Invoice no" values don't correspond to anything in
    the Invoice sheet, so receipts are linked to a transaction by matching
    customer name + closest date on/before the receipt date. Receipts for a
    customer with no matching transaction are skipped and counted below.
  - The "Stock maintain" sheet is a free-form, inconsistent layout (two
    side-by-side mini-tables, some categories with no counts) and is not
    imported; materials/stock come from what's referenced in Invoice and
    Product purchase instead, so stock counts should be treated as a
    starting point to correct by hand, not ground truth.
"""
import openpyxl
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from rentals.excel_import import run_import, ExcelImportError


class Command(BaseCommand):
    help = "Import customers/rentals/receipts/payments/expenses from docs/source-data/SSMSALES_and_EXPENSES.xlsx"

    def handle(self, *args, **options):
        xlsx_path = settings.BASE_DIR.parent / "docs" / "source-data" / "SSMSALES_and_EXPENSES.xlsx"
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        try:
            with transaction.atomic():
                stats = run_import(wb)
        except ExcelImportError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS("Import complete:"))
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}")
