# Change request batch — 2026-11

Status: **spec only — not yet implemented.** This is the plan to review/approve before any of it is built. Builds on [`spec.md`](./spec.md) (the 1.0 spec); items here are either 1.0 refinements or pulled forward from 1.0 §9's open questions / 2.0 candidates.

Source material (provided by the owner, kept here for reference — do not edit, these are the design/format source of truth):
- [`branding/ssm-logo.pdf`](./branding/ssm-logo.pdf) — the real vector logo.
- [`branding/ssm-invoice-template.pdf`](./branding/ssm-invoice-template.pdf) — the exact invoice layout to match.
- [`branding/rate-unit-reference.png`](./branding/rate-unit-reference.png) — a screenshot showing a "Rate Unit" dropdown (Per piece/day, Per ft/day, Per piece/20 days, Per ft/20 days, Per piece/30 days) from a reference tool, informing item 7 below.

## 1. Real logo everywhere

Replace the hand-approximated placeholder at `webapp/rentals/static/rentals/img/logo.svg` with the actual vector mark from `branding/ssm-logo.pdf` (navy `SS`, green `M`, navy/green skyline icon, "CENTRING RENTALS" wordmark). Same file path, so `_sidebar_nav.html` and `login.html` need no template change — just new file content, traced/exported from the real vector source instead of approximated.

Applies to every page that currently shows the logo: login page, sidebar (all authenticated pages).

## 2. Purchase Bill — multiple line items per bill

**Current state:** `ProductPurchase` is a flat single-line record (date, category, size, count, rate, amount) — no concept of "one purchase bill with several items on it," unlike rentals which already have `RentalTransaction` (header) + `RentalLineItem` (lines).

**Change:** mirror that same pattern for purchases:

```
PurchaseBill                 (NEW — header, one per vendor bill)
  id, bill_number, date, vendor_name, remarks, created_at

ProductPurchase               (becomes a line item under a bill)
  id, bill (FK to PurchaseBill, NEW), category (FK), size_label, count, rate, amount
```

- New screen `purchases/new/` (same dynamic-add-row UX as `rental_form.html`'s material line items — reuse that JS pattern): pick/enter vendor + date, add N line items (category, size, count, rate → amount), save as one bill.
- Purchase list page groups/links by bill; existing per-line edit/delete stays available at the line level.
- `bill_number` auto-generated sequentially, same convention as `RentalTransaction.invoice_number` (e.g. `SSM/PUR/0001`).

## 3. Dashboard — Receipts & Payments widgets

**Current state:** dashboard shows aggregate cash in/out, pending amounts, deposits held, low-stock, recent transactions (spec.md §4 item 1) — no dedicated Receipts/Payments breakout.

**Change:** add two explicit cards/widgets:
- **Receipts** — today's total + this month's total, money received (green).
- **Payments** — today's total + this month's total, money paid out (red).

Distinct from the existing "cash in/out this month" summary card: these are per-category call-outs so the owner can see receipts vs. payments at a glance without opening either list.

## 4. Customer — expanded profile fields

**Current state:** `Customer` has `name, phone, place, aadhar_number` only (spec.md §3).

**Change — new fields:**

```
Customer
  id, customer_id (NEW, e.g. "SSM-CUS-0001", auto-generated, sequential, read-only),
  name, phone, place,
  address (NEW), pincode (NEW),
  construction_site_address (NEW),
  customer_type (NEW — choices: Contractor, Builder, Owner, Mason),
  payment_terms (NEW — free text, e.g. "Rent ₹X/day, Advance ₹Y" — kept free-text since
    advance/rent terms vary per customer and don't need their own structured fields),
  aadhar_number, created_at
```

- `customer_id` generated the same way `invoice_number` already is (sequential counter, `SSM-CUS-####` format), shown but not editable on the form.
- `customer_type` as a dropdown (`forms.Select`), matching the existing widget style.
- All new fields added to `CustomerForm`, the customer list/detail display, and the Excel importer's customer-matching logic (new fields default blank for rows that predate this change — no backfill from the existing sheet, which doesn't have them).

## 5. Dashboard — material due back this month

**Current state:** `RentalLineItem` has `days_estimated` but no stored due-date; nothing on the dashboard surfaces upcoming returns (spec.md §9 lists reminders for pending returns as a 2.0 candidate — pulling this forward).

**Change:**
- Add a computed **due date** = `transaction.date_out + line_item.days_estimated` (no new stored column needed — computed property on `RentalLineItem`, same approach as the existing bill-amount calculation).
- New dashboard widget: **"Material due back this month"** — table of open/partially-returned line items whose due date falls in the current calendar month, showing customer name, material, due date, days overdue (if past due, highlighted red).

## 6. Invoice generation — print/download matching the real format

**Current state:** no invoice document exists — `RentalTransaction` data is only ever viewed on-screen (`rental_detail.html`).

**Change:**
- Add a **"Generate Invoice"** button on the rental detail page (`rental_detail.html`), linking to a new route `rentals/<pk>/invoice/`.
- That page (`invoice.html`) renders the transaction in the **exact layout of `branding/ssm-invoice-template.pdf`**: navy header band with green diagonal accent, logo, "SRI SAI MURUGAN CENTRING RENTALS" + "Right Material / Right Price" tag pills, phone numbers + address block, "INVOICE" title, Invoice No. (`SSM/INV/####`) + Date, Customer Name / Contact Number / Site Location, a S.No/Description/Qty/Rate/Amount line-items table, Subtotal / Transportation / Grand Total, Terms & Conditions list (the same 4 standard terms from the template), signature lines (Customer Signature / Authorized Signature), footer band repeating the phone numbers.
- A **"Print Invoice"** button on that page triggers the browser's native print dialog (`window.print()`) with a dedicated `@media print` stylesheet so it renders cleanly to paper or "Save as PDF" (every modern browser's print dialog offers Save-as-PDF — no new backend dependency, no `wkhtmltopdf`/`weasyprint`/`reportlab` package needed, keeps the single-EC2 deploy simple per spec.md §2's existing stance on avoiding extra moving parts). The on-screen and printed views are the same template; print CSS hides the app chrome (sidebar/topbar) and fixes the page to A4.
- "Transportation" is a new optional field on `RentalTransaction` (defaults to 0) so the invoice's Subtotal/Transportation/Grand Total breakdown has real numbers, not blank lines.

## 7. Additional improvements (proposed, not requested verbatim — flagging for approval)

- **Flexible rate units on Material** — `rate-unit-reference.png` shows a reference tool offering "Per piece/day," "Per ft/day," "Per piece/20 days," "Per ft/20 days," "Per piece/30 days." Today `Material.default_rate_per_day` hardcodes "per day." Proposed: add `rate_unit` (choices matching the above) to `Material` and `RentalLineItem`, and adjust the line-amount calculation to divide/multiply by the unit's day-count instead of assuming 1. Flagging as optional since it changes the core billing formula (spec.md §3.1) — worth confirming this matches how SSM actually quotes rates before building it.
- **Transportation charge, line-item damage charges, and rounding** — the invoice template's Terms & Conditions mention "Damaged materials will be charged separately," which nothing in the current data model captures. Proposed as a simple optional `damage_charge` amount on `RentalTransaction` (manually entered at return time), rolled into the Grand Total on the invoice — not a full damage-tracking subsystem.
- **Customer ID / Invoice No. visible on customer & rental list pages**, not just detail pages, now that both are real identifiers staff will reference verbally with customers on the phone.

## 8. Suggested build order

Roughly independent pieces — can land as separate PRs in any order, but this grouping minimizes rework:

1. Logo swap (item 1) — fast, zero risk, do first.
2. Customer fields (item 4) — self-contained model + form change.
3. Dashboard widgets (items 3, 5) — read-only, additive, no schema risk beyond the due-date property.
4. Purchase Bill restructure (item 2) — touches an existing model's shape (adds a required FK), needs a migration + data backfill plan for existing `ProductPurchase` rows (wrap each in a generated single-line `PurchaseBill`).
5. Invoice generation (item 6) — depends on nothing above except optionally the new `Transportation`/`damage_charge` fields.
6. Item 7's rate-unit change last, if approved — it's the one item that touches the billing formula, so it should land once everything else is stable and tested.
