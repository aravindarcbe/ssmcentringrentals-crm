# SSM Centring Rentals — CRM

CRM for a centring/shuttering equipment rental business: material inventory, customer records, rental billing (advance + return settlement), and expense tracking.

See [`docs/spec.md`](docs/spec.md) for the full specification, data model, tech stack decision, and AWS hosting cost breakdown.

The owner's original manual tracker is kept for reference at [`docs/source-data/SSMSALES_and_EXPENSES.xlsx`](docs/source-data/SSMSALES_and_EXPENSES.xlsx).

**Stack:** Django + PostgreSQL, single AWS EC2 instance.

## Running it locally

No AWS, no Postgres install needed for local dev — SQLite is used by default.

```bash
cd webapp
./setup.sh
```

This creates a virtual environment, installs dependencies, runs database migrations, prompts you to create an admin login (first run only), and starts the dev server.

Then open:
- **`http://127.0.0.1:8000/`** — the dashboard
- **`http://127.0.0.1:8000/admin/`** — CRUD screens for Customers, Materials, Rental transactions (with material lines, deposit, and receipts inline), Payments, Product purchases, and Daily expenses

To see the app with data instead of an empty database, you have two options (from inside `webapp/`, with the virtual environment active):

- **Real data from the owner's Excel tracker:** `python manage.py import_excel_data` — imports customers, rental transactions, receipts, payments, purchases, and expenses from `docs/source-data/SSMSALES_and_EXPENSES.xlsx`. See the notes at the top of `rentals/management/commands/import_excel_data.py` for its matching limitations (it's a best-effort import of a manually-kept spreadsheet, not a lossless migration).
- **Made-up sample data:** `python manage.py seed_demo_data`

Run only one of these against a fresh database (delete `webapp/db.sqlite3` first if you want to switch or re-run).

To view it from your phone on the same WiFi, run `python manage.py runserver 0.0.0.0:8000` instead and open `http://<your-computer-IP>:8000` from the phone.
