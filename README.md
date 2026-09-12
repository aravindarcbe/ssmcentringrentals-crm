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

## Renaming/removing a personal admin account

If `createsuperuser` was run without typing a username, it defaults to your OS username (e.g. your Windows login name) — that then shows up in the app (sidebar avatar, admin "Welcome, ..." text). To fix it without losing the account:

1. Log into `/admin/`
2. Go to **Authentication and Authorization → Users**
3. Click the account showing your personal name
4. Change the **Username** field to something generic (e.g. `admin`), Save

Nothing in the code hardcodes any name — this is purely local account data.

## Google sign-in ("Sign in with Google")

The login page can show a "Sign in with Google" button (Django's own admin login page, and anywhere else `staff_member_required` redirects to it). It's hidden by default and only appears once both `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` are set in `webapp/.env`.

To get those values:
1. Go to [console.cloud.google.com](https://console.cloud.google.com/) → create/select a project
2. **APIs & Services → OAuth consent screen** — set it up (External type is fine for a small business tool; keep it in "Testing" status and add your own Gmail address as a test user to skip Google's verification review)
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → Application type **Web application**
4. Under **Authorized redirect URIs**, add: `http://127.0.0.1:8000/accounts/google/login/callback/` (add the production URL's equivalent once deployed to AWS)
5. Copy the **Client ID** and **Client Secret** into `webapp/.env`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=your-client-id
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   ```
6. Restart the server

**Important:** a new account created by signing in with Google has no admin access by default (safe default — it doesn't just let anyone with a Gmail account in). After someone signs in with Google for the first time, grant them access the same way as above: **Users** → find their account → check **Staff status** (and **Superuser status** if they should have full access).
