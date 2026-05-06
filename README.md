# Django Ecommerce (Stride template) + Settings + Tracking

This project scaffolds a multi-app Django system with:
- Ecommerce basics (`products`, `orders`)
- Inventory basics (`inventory`)
- Accounting basics (`accounts`) with a simple ledger
- Dynamic settings (`settings`) including duplicate-order defense
- Order tracking timeline (`orders`)
- DRF APIs (token auth) + server-rendered pages

## Quickstart

```powershell
python manage.py migrate
python manage.py runserver
```

Admin:
```powershell
python manage.py createsuperuser
python manage.py runserver
```

Then open:
- `http://127.0.0.1:8000/` (storefront)
- `http://127.0.0.1:8000/admin/` (admin)

## Dynamic Settings (DB-driven)

Settings table: `apps.settings.models.Setting`
- `duplicate_order_enabled` (`0`/`1`)
- `duplicate_order_days` (integer days)

Edit in admin:
- Admin → Settings → Settings

Helper access:
- `core/utils/settings_loader.py`

## Duplicate Order Defense

Enforced when placing orders via:
- Checkout page (session cart)
- API order creation

Logic:
- Enabled by `duplicate_order_enabled`
- Window = `duplicate_order_days`
- Ignores cancelled orders

Implementation:
- `apps/orders/services.py` (`enforce_duplicate_order_restriction`)

## Order Tracking

Statuses:
`pending → confirmed → processing → shipped → delivered` (plus `cancelled`)

Tracking events:
- `apps.orders.models.OrderTracking`
- Auto-created on order create/status change via `apps/orders/signals.py`

Pages:
- Track lookup: `GET/POST /track-order/`
- Timeline: `GET /orders/<public_id>/tracking/`

APIs:
- Public tracking: `GET /api/orders/track/<public_id>/`
- Authenticated orders CRUD: `GET/POST /api/orders/`
- Status change (staff/admin): `PATCH /api/orders/<public_id>/status/`

## Prefix/Custom IDs

Generated IDs:
- Order: `ORD-1/05-26` (monthly reset)
- Product: `PRD-1/05-26` (monthly reset)
- Income: `INC-1/05-26` (monthly reset)
- Expense: `EXP-1/05-26` (monthly reset)
- Purchase: `PUR-0000001/26` (yearly reset)
- User: `UID-0000001/26` (yearly reset)

Implementation:
- `core/utils/id_generator.py`

## Template assets

Static assets copied into:
- `static/solestyle/_astro/Base.B5hAE-Ox.css`
- `static/solestyle/favicon.svg`

Templates:
- `templates/base.html`
- `templates/includes/navbar.html`
- `templates/includes/footer.html`
- `templates/pages/*.html`
