# SENAITE Billing — Design & Functionality

> Status: **Proposal / design spec** for a `senaite.billing` add-on (or an in-core
> `senaite.core.billing` module). Nothing here is wired up yet — this document
> describes what to build and how it plugs into the existing SENAITE architecture.

## 1. Why this, and what already exists

SENAITE already ships the **pricing** half of billing. Do **not** reimplement it:

| Concern | Where it already lives |
|---|---|
| Per-analysis price / bulk price / VAT | `AnalysisService` price fields |
| Client discounts | `Client` → `BulkDiscount`, `MemberDiscount` |
| Price lists | `Pricelist` / `PricelistFolder` content types |
| Per-sample money API | `AnalysisRequest.getSubtotal()`, `getSubtotalVATAmount()`, `getDiscountAmount()`, `getVATAmount()`, `getTotalPrice()` (see [analysisrequest.py:1900](../src/bika/lims/content/analysisrequest.py#L1900)) |
| Show/hide prices | `ShowPrices` setup flag ([ShowPrices doctest](../src/senaite/core/tests/doctests/ShowPrices.rst)) |

What is **missing** — and what this feature adds — is everything downstream of a
priced sample:

- **Invoice** — a billable document that groups the priced work for a client.
- **Invoice Batch** — a periodic run that generates many invoices at once
  (e.g. "invoice everything published in June").
- **Payment tracking** — issued → paid / partially paid / overdue, with payments.
- **Invoice numbering, currency, tax rules** at the lab level.
- **PDF rendering** of an invoice via `senaite.impress`.
- **Listings, controlpanel, and JSON API** for all of the above.

The golden rule: **an Invoice never recomputes prices.** It snapshots
`sample.getTotalPrice()` (and the subtotal/discount/VAT breakdown) at issue time,
so later price-list changes never mutate a historical invoice.

## 2. Content types (Dexterity)

New types live under `senaite.core.content` (subclassing `Container`/`Item` from
[content/base.py](../src/senaite/core/content/base.py)), registered via
`configure.zcml` + a GenericSetup profile. New types should be **Dexterity**, per
[CLAUDE.md](../CLAUDE.md).

```
/senaite/invoices                      InvoiceBatchFolder (Container)
   └── B-2026-0001                     InvoiceBatch      (Container)
         ├── INV-000001                Invoice           (Container)
         │     ├── <line>              InvoiceLineItem   (Item)   ← one per analysis/sample
         │     └── <payment>           Payment           (Item)   ← zero or more
         └── INV-000002                Invoice
```

### 2.1 `InvoiceBatch`
A periodic invoicing run. Folderish; holds the generated invoices.

| Field | Type | Notes |
|---|---|---|
| `title` | TextLine | e.g. "June 2026" |
| `date_from` / `date_to` | Datetime | selection window (by sample **published** date) |
| `client` | UIDReference → Client | optional; empty = all clients |
| `notes` | Text | |

Actions: **Generate** (create invoices for all matching samples), **Issue all**,
**Export** (CSV/PDF bundle).

### 2.2 `Invoice`
One billable document for one client.

| Field | Type | Notes |
|---|---|---|
| `invoice_number` | TextLine (auto) | via ID server, format configurable (§6) |
| `client` | UIDReference → Client | frozen at creation |
| `client_address` | Address snapshot | billing address at issue time |
| `invoice_date` | Datetime | date issued |
| `due_date` | Datetime | `invoice_date + payment_terms_days` |
| `currency` | TextLine | from lab setup |
| `subtotal` / `discount` / `vat` / `total` | Decimal (snapshot) | sum of line items |
| `amount_paid` | Decimal (computed) | Σ payments |
| `remarks` | Text (Remarks behavior) | reuse `senaite.core.api.remarks` |

Read-only computed: `getBalanceDue() = total - amount_paid`.

### 2.3 `InvoiceLineItem`
One row on the invoice — snapshots a single billed analysis (or a whole sample,
configurable granularity).

| Field | Notes |
|---|---|
| `source_uid` | UID of the `Analysis` / `AnalysisRequest` billed |
| `sample_id` | denormalized Sample ID for printing |
| `description` | analysis title / keyword |
| `quantity` | default 1 |
| `unit_price` / `discount` / `vat_pct` / `line_total` | snapshot |

### 2.4 `Payment`
| Field | Notes |
|---|---|
| `payment_date` | |
| `amount` | Decimal |
| `method` | Choice — cash / card / transfer / cheque (vocabulary) |
| `reference` | transaction ref |

## 3. Workflow

A DCWorkflow `senaite_invoice_workflow`, defined in
`profiles/default/workflows/senaite_invoice_workflow/definition.xml`, with guards
and transition side-effects in code under
`senaite/core/workflow/invoice/` (mirrors the existing
[workflow layout](../src/bika/lims/workflow/)).

```
        ┌────────┐  issue   ┌────────┐  pay (full)     ┌──────┐
        │ draft  │─────────▶│ issued │────────────────▶│ paid │
        └────────┘          └────────┘                 └──────┘
             │                  │  pay (partial)  │
          cancel                │        ▼        │ pay (remainder)
             ▼                  │  ┌──────────────┐
        ┌──────────┐            └─▶│ partially_   │
        │ cancelled│               │ paid         │
        └──────────┘               └──────────────┘
                              (overdue = issued/partially_paid AND due_date < today)
```

States: `draft`, `issued`, `partially_paid`, `paid`, `cancelled`.
`overdue` is **not** a stored state — it's a catalog-derived flag
(`is_overdue` index) so a nightly reindex, not a transition, keeps it truthful.

**Transition side-effects**
- `issue`: freeze snapshots, assign `invoice_number` (ID server), set `due_date`,
  stamp the source analyses as `billed=True` so they aren't double-invoiced.
- `pay`: append a `Payment`; recompute `amount_paid`; auto-advance to
  `partially_paid` or `paid` via a guard on the balance.
- `cancel`: only allowed from `draft`; releases the `billed` flag on sources.

Guards live in `workflow/invoice/guards.py`; e.g. `guard_issue` requires ≥1 line
item and a non-zero total.

## 4. Generation flow (the core use case)

```
InvoiceBatch.generate():
  samples = senaite_catalog_sample(
      review_state="published",
      getDatePublished=(date_from, date_to),
      billed=False,
      client_uid=<client or all>)
  group samples by client
  for client, client_samples in groups:
      invoice = create Invoice(container=batch, client=client)
      for sample in client_samples:
          for analysis in sample.getBillableAnalyses():
              add InvoiceLineItem(snapshot of analysis price)
      invoice.recalculate()          # subtotal/discount/vat/total from lines
  log a summary: N invoices, M samples, skipped (no price / already billed)
```

Only **published** samples with a price are billable. A sample already covered by
an issued invoice (`billed=True`) is skipped — surfaced in the run log, never
silently dropped.

## 5. Catalog & indexes

Add a dedicated catalog `senaite_catalog_invoice` (pattern:
[catalog/](../src/senaite/core/catalog/)). Index naming follows
[docs/conventions/catalogs.rst](conventions/catalogs.rst) — lowercase, singular:

| Index | Type | Purpose |
|---|---|---|
| `client_uid` | Field | invoices for a client |
| `invoice_date` / `due_date` | Date | period & ageing queries |
| `review_state` | Field | listing filters |
| `is_overdue` | Boolean | ageing dashboards |
| `getInvoiceNumber` | Field (metadata) | search / column |

Add a `billed` **boolean index** to `senaite_catalog_sample` so generation can
exclude already-invoiced samples cheaply.

## 6. Lab-level settings (registry / setup)

Extend the SENAITE setup (`senaite.core.registry` /
[content/senaitesetup.py](../src/senaite/core/content/senaitesetup.py)) with a
**Billing** fieldset:

- `currency` (ISO 4217, default from lab locale)
- `default_vat` (%) — falls back to existing per-service VAT
- `payment_terms_days` (due-date offset, default 30)
- `invoice_id_format` — ID server template, e.g. `INV-{seq:06d}`
- `invoice_batch_id_format` — e.g. `B-{year}-{seq:04d}`
- `bank_details` / `tax_id` — printed on the PDF footer

ID formats are registered in the **ID server**
([idserver](../src/senaite/core/idserver/)) so numbering is gap-free and
lab-configurable, exactly like Sample IDs.

## 7. UI

Listings reuse `senaite.app.listing` (React) — the same engine as the Samples
view you saw running:

- **Invoices** listing at `/senaite/invoices` — columns: number, client, date,
  due, total, balance, state; state-based filter tabs (Draft / Issued / Overdue /
  Paid); batch actions **Issue** and **Add payment**.
- **Invoice batches** listing — with a **Generate** button.
- **Invoice view** — line items table + payments table + a "Record payment" form;
  workflow buttons from the state.
- **Client → Invoices** viewlet — invoices filtered to that client.
- **PDF** — an `senaite.impress` report template (`Invoice.pt`) so invoices print
  with the same engine as Sample reports; "Download PDF" / "Email to client".
- **Dashboard panel** — outstanding balance, overdue count, revenue this period.

## 8. JSON API

Because it's Dexterity + catalog, it works through `senaite.jsonapi` for free:

```
GET  /@@API/senaite/v1/search?portal_type=Invoice&review_state=issued
POST /@@API/senaite/v1/create   {portal_type: "Invoice", ...}
POST /@@API/senaite/v1/update   {uid, transition: "issue"}      # fire workflow
POST /@@API/senaite/v1/update   {uid, transition: "pay", amount: 50}
```

Add thin convenience routes for the two aggregate actions:
`POST /@@API/senaite/v1/invoicebatch/<uid>/generate` and
`.../invoice/<uid>/pay`.

## 9. Permissions & roles

New permissions in `senaite.core.permissions` (pattern:
[permissions/](../src/senaite/core/permissions/)):
`senaite.core: Add Invoice`, `View Invoices`, `Issue Invoice`, `Record Payment`,
`Cancel Invoice`. A **Biller / Accountant** role gets billing perms without lab
result-entry rights; **LabManager** inherits all. Wire into `rolemap.xml`.

## 10. Events / integration

Subscribers under `senaite/core/subscribers/`:
- On **sample published** → (optional setting) auto-add to the current open
  `InvoiceBatch`, or just leave it billable for the next run.
- On **sample cancelled/invalidated after invoicing** → flag the invoice for
  review (never silently mutate an issued invoice).

## 11. File layout (implementation map)

```
src/senaite/core/
  content/invoice.py            invoicebatch.py  invoicelineitem.py  payment.py
  workflow/invoice/             guards.py  events.py
  catalog/invoice_catalog.py
  browser/invoices/             view.py  templates/  static/
  permissions/                  (+ invoice perms)
  profiles/default/
    types/Invoice.xml  InvoiceBatch.xml  ...
    workflows/senaite_invoice_workflow/definition.xml
    workflows.xml  catalog.xml  registry.xml  rolemap.xml
  upgrade/v02_08_000.py         (+ zcml)        # install catalog, types, workflow
  tests/doctests/               Invoice.rst  InvoiceBatchGenerate.rst  InvoiceWorkflow.rst
impress template:               Invoice.pt
```

Any change to stored data/catalogs/profile needs an **upgrade step**
(`vXX_YY_ZZZ.py`), per [upgrade/README.rst](../src/senaite/core/upgrade/README.rst)
— here: register the new catalog, content types, workflow, and the `billed`
sample index; reindex.

## 12. Testing

Textual doctests (the SENAITE norm — see
[test_textual_doctests.py](../src/senaite/core/tests/test_textual_doctests.py)):

- `Invoice.rst` — price snapshot is frozen at issue; later price change doesn't
  alter an issued invoice.
- `InvoiceBatchGenerate.rst` — only published, unbilled, priced samples are
  invoiced; grouped by client; double-run invoices nothing new.
- `InvoiceWorkflow.rst` — draft→issue→partial→paid; balance guard; cancel only
  from draft and releases `billed`.

## 13. Build order (milestones)

1. **M1 — model**: content types + catalog + GS profile + upgrade step. Create an
   Invoice by hand in the UI, see it listed.
2. **M2 — pricing snapshot**: line items from a sample's billable analyses;
   `recalculate()`; totals match `sample.getTotalPrice()`.
3. **M3 — workflow**: issue/pay/cancel + ID numbering + `billed` flag.
4. **M4 — batch generation**: the §4 flow + run log.
5. **M5 — payments & ageing**: Payment type, `is_overdue`, dashboard panel.
6. **M6 — PDF & email** via `senaite.impress`.
7. **M7 — JSON API convenience routes + docs**.

---

### Smallest useful first slice
If you want something running fast: **M1 + M2 + M3 for a single manually-created
Invoice** (skip batches and payments). That already demonstrates the whole idea —
a priced sample becoming an issued, numbered invoice — and everything else layers
on top.
