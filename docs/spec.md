# SSM Centring Rentals — CRM Specification

Status: **Draft v1** — approved tech stack, ready for implementation planning.
Source of truth for business data: [`source-data/SSMSALES_and_EXPENSES.xlsx`](./source-data/SSMSALES_and_EXPENSES.xlsx) (the owner's existing manual tracker, kept in this repo for reference — do not edit it; it documents the real-world workflow this CRM replaces).

## 1. Business context

SSM rents out centring/shuttering equipment (jockeys, sheets, spans, runners, wood planks of various sizes) to construction clients. Today this is tracked by hand in the referenced Excel workbook across 8 sheets. This CRM replaces that workbook with a proper web app while preserving the exact workflow the owner already relies on.

### 1.1 What the existing sheets tell us

| Sheet | Purpose | Key columns |
|---|---|---|
| Client Details | Customer master | Client name, Phone number, Place, Aadhar Number |
| Invoice | Rental transactions, line-item per material | Date, Client name, Phone, Products, Count, Ft, Days, Rate, Bill amount, Paid, Pending amount, Discount, Deposit amount, Reminder/status, Remarks |
| Recepit | Money received against invoices | Payment received date, Invoice no, Client name, Amount, Payment mode, Balance deposit amount |
| Payment | Money paid out (salary, loans, misc.) | Date, Description, Client/payee, Amount, Payment mode |
| Product purchase | Stock acquisition costs | Date, Category, Size, Count, Rate, Amount |
| Daily expense | Day-to-day operating expenses | Date, Category, Description, Amount, Payment mode |
| Stock maintain | Inventory on hand + what's checked out to whom | Category, Size, Total count, and a side table of Date/Client/Size/Count checked out |
| Dash board | (currently empty placeholder in the sheet) | — |

### 1.2 Core workflow to digitize

1. **Add materials** — define rentable items (category e.g. Jockey/Sheet/Span/Runner/Wood-plank, size e.g. "12 inch 8 ft", rental rate) and track stock counts.
2. **Add customers** — name, phone, place, Aadhar number.
3. **Rent out material ("bill on advance")** — pick a customer, add one or more material lines (material, count, size/ft, days, rate → line amount), record an advance/deposit received. This opens a rental transaction and reduces available stock for those items.
4. **Track running cash** — every amount received against a transaction is logged with date, mode (Cash/GPay/Card/Bank), so pending balance is always known per transaction and per customer.
5. **Return material ("bill on return")** — when material comes back, record actual days used and quantity returned. The system computes the **final bill** (actual usage × rate), compares it to the **deposit already held**:
   - Deposit > final bill → **refund due to customer**.
   - Deposit < final bill → **balance due from customer**.
   Returned stock goes back into available inventory.
6. **Expense tracking** — outgoing Payments (salary/loans/misc.), Product purchases (stock buy-ins), and Daily expenses (operating costs), each with category, amount, payment mode, date — mirroring the three expense-related sheets.
7. **Dashboard** — cash position (received vs paid out), open pending amounts, deposits currently held, low-stock materials, recent activity.

## 2. Tech stack (decided)

| Layer | Choice | Why |
|---|---|---|
| Backend + Admin CRUD | **Django** (Python) + Django admin | Most of this app is tabular data entry (materials, customers, expenses) — Django admin gives working CRUD screens for free; custom views/templates only needed for the rental → return billing workflow and the dashboard. |
| Database | **PostgreSQL**, self-hosted on the same EC2 instance | Relational schema matches the sheets naturally (customers, transactions, line items, ledgers with foreign keys). Self-hosting avoids RDS's 12-month free-tier expiry. |
| Frontend | Django templates + Bootstrap (server-rendered), minimal JS (Alpine.js or vanilla) for the multi-line-item invoice form | No SPA build pipeline needed; keeps the single-EC2 deploy simple. Can be revisited later if a richer UI is wanted. |
| Hosting | **One AWS EC2 instance** (t3.micro or t4g.micro), Nginx + Gunicorn + Postgres all on the same box | Free for 12 months under AWS Free Tier (750 hrs/month); after that, ~$6-9/month total — the only ongoing cost, no separate DB bill. |
| Static/media files | Served by Nginx from local disk (or optionally S3 free tier — 5GB — later if needed) | Keeps everything on one box for now; low traffic doesn't need CDN. |
| Backups | Nightly `pg_dump` cron job, rotated locally + optionally pushed to S3 free tier (5GB) | Cheap insurance against instance loss. |
| Domain/SSL | Let's Encrypt (free) via Certbot, any domain registrar of choice | No cost beyond domain registration (~$10-15/year if a custom domain is wanted; not required — can use the EC2 public IP or a free subdomain initially). |
| Auth | Django's built-in auth (staff accounts for the owner + employees) | No external auth service needed at this scale. |

**Cost summary:** $0 for the first 12 months; **~$6-9/month indefinitely after that** (one EC2 instance, no RDS). See §7 for the full breakdown.

## 3. Data model

```
Customer
  id, name, phone, place, aadhar_number, created_at

MaterialCategory        (e.g. Jockey, Sheet, Span, Runner, Wood Plank)
  id, name

Material                (a specific rentable size/variant within a category)
  id, category (FK), size_label (e.g. "12 inch 8 ft"), ft_value, default_rate_per_day,
  total_stock_count, available_count

RentalTransaction        ("Invoice" in the old sheet — one per rental event)
  id, invoice_number, customer (FK), date_out, status [OPEN, PARTIALLY_RETURNED, CLOSED],
  discount, remarks, created_at

RentalLineItem            (one row per material within a transaction)
  id, transaction (FK), material (FK), count, days_estimated, rate,
  line_amount (count * ft * rate, matching sheet logic),
  count_returned, date_returned, days_actual

DepositLedger             (advance/deposit tracking per transaction)
  id, transaction (FK), amount_collected, amount_refunded, balance_held

Receipt                   (money received — advance, part-payment, or final settlement)
  id, transaction (FK), date, amount, payment_mode [Cash, GPay, Card, Bank], note

Payment                   (money paid out — salary, loan, misc.)
  id, date, description, payee, amount, payment_mode

ProductPurchase            (stock buy-ins)
  id, date, category (FK), size_label, count, rate, amount

DailyExpense
  id, date, category, description, amount, payment_mode

StockMovement              (audit trail: rented out / returned, drives available_count)
  id, material (FK), transaction (FK), direction [OUT, IN], count, date
```

### 3.1 Return / refund calculation

On return of a `RentalLineItem`:

```
actual_days = date_returned - date_out
final_line_amount = count_returned * ft_value * rate * actual_days_factor   # matches existing sheet convention
transaction.final_bill = sum(final_line_amount for all line items)
net_position = deposit_ledger.amount_collected - transaction.final_bill - discount
  if net_position > 0: refund_to_customer = net_position
  if net_position < 0: balance_due_from_customer = abs(net_position)
```

(Exact multiplication convention — whether `days` factors into the line amount or is informational only — will be confirmed against how the owner actually bills, since the sample sheet uses `Ft × Rate` per line without always multiplying by days. This is a decision to confirm during implementation, not a schema change.)

## 4. Screens / modules

1. **Dashboard** — total cash in / out this month, open pending amounts, deposits currently held, low-stock alerts, recent transactions.
2. **Materials** — list/add/edit categories and sizes, stock counts, default rates.
3. **Customers** — list/add/edit customer details.
4. **New Rental (bill on advance)** — pick customer, add material lines, capture advance received, generate invoice number.
5. **Rental detail / Return (bill on return)** — view a transaction, mark items returned, system computes final bill and refund/balance due, record the settling receipt or refund payment.
6. **Receipts** — list of all money received, filterable by customer/date/mode.
7. **Payments** — outgoing payments log.
8. **Product Purchases** — stock buy-in log.
9. **Daily Expenses** — operating expense log.
10. **Reports** — pending amounts by customer, deposits held, monthly cash flow, expense category breakdown.

## 5. Non-functional requirements

- Single-tenant, internal tool — a handful of staff logins, no public signup.
- Mobile-friendly (Bootstrap responsive) since data entry may happen on-site from a phone.
- All monetary figures in INR.
- Dates stored as proper `Date` fields (the source sheet's `DD.M.YYYY` text format is a data-entry artifact to fix, not to replicate).

## 6. Deployment plan (high level)

1. Provision one EC2 instance (t3.micro/t4g.micro, Ubuntu), free-tier eligible.
2. Install Postgres, Python/Django, Nginx, Gunicorn on the instance.
3. Django app + Gunicorn managed via systemd; Nginx reverse-proxies to Gunicorn and serves static files.
4. Certbot for free SSL once a domain is pointed at the instance's Elastic IP.
5. Nightly `pg_dump` cron → local rotation (+ optional S3 push later).
6. CI: GitHub Actions (free for public/private repos within free minutes) to run tests on push; manual or simple script-based deploy (`git pull` + restart service) to start, revisit automation later.

## 7. AWS cost breakdown

| Period | Item | Cost |
|---|---|---|
| Months 1-12 | EC2 t3.micro/t4g.micro, 750 hrs/month | $0 (Free Tier) |
| Months 1-12 | EBS storage up to 30GB | $0 (Free Tier) |
| Ongoing (always free) | Data transfer out, first 100GB/month | $0 |
| Month 13+ | EC2 t3.micro/t4g.micro, 24/7 | ~$6-9/month |
| Month 13+ | EBS storage (~20-30GB) | ~$2-3/month |
| Optional | Custom domain registration | ~$10-15/year |
| **Total after month 12** | | **~$6-9/month** (no RDS, no other AWS services required) |

No other AWS services (RDS, Lambda, DynamoDB, Amplify, Cognito) are required for this stack, so there is exactly one recurring line item to budget for.

## 8. Open questions to confirm with the owner during build

- Exact billing formula for partial-day / multi-day rentals (does `Days` multiply into the bill amount, or is the rate already a flat period rate as in the sample sheet?).
- Whether discounts apply per line item or per whole transaction.
- Whether Aadhar number needs to be masked/restricted for privacy given it's sensitive PII.
- Multi-user roles (owner vs. staff) and whether staff should see all financials or only their own entries.
