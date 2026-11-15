# Textile ERP

Frappe v15 app foundation for textile inventory, material formulas, production,
employee records, attendance, leave requests, and a guest-facing product catalog.

The app is designed to run on Frappe Framework only. It does not depend on
ERPNext or the official Frappe HRMS app.

## Development

This app is linked into the WSL bench at `~/frappe-v15-bench`. From Ubuntu:

```bash
cd ~/frappe-v15-bench
bench --site frappe.local install-app textile_erp
bench start
```

Create `frappe.local` first with `bench new-site frappe.local`; the command
prompts for the local database and site administrator credentials.

Customer email verification requires the site's Frappe Fernet-format
`encryption_key`. If it is missing or was generated in the wrong format, set
one once from the bench directory with
`bench --site frappe.local set-config encryption_key "$(./env/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')`,
then restart the Frappe processes. Frappe requires a 32-byte URL-safe Base64
Fernet key; do not use `openssl rand -hex`. In local development, stop
`bench start` with **Ctrl+C** in its terminal and run `bench start` again;
`bench restart` does not restart a development bench. Do not commit or replace
an already-valid key. If the site had a previous valid key that was lost,
restore that original key rather than generating a replacement.

## Product catalog API

The guest endpoints expose only products marked **Publish on Website**:

- `textile_erp.api.get_products`
- `textile_erp.api.get_product`

Raw materials, stock balances, and internal employee data are not included in
the public catalog response.

For an apparel product, fill **Colors and Images** with each customer-facing
color and its public image, then add a **Size and Color Stock** row for every
available color/size combination with its quantity. Sizes are free text, so
standard sizes (XS through XXL) and product-specific labels are supported.
Customers choose color and size before adding a variant to their bag. The app
checks the quantity on bag updates and reserves it when an order is placed;
changing a reserved order to **Cancelled** restores that stock. Existing
products with no color or variant rows continue to work as single-option items.
Variant quantities are maintained on the product and are not automatically
distributed from the existing item-level production stock ledger.

## Initial HR scope

The custom HR module includes departments, employee records, attendance, and
leave requests with employee self-service and HR Manager permissions. Payroll,
recruitment, statutory calculations, and biometric integrations are not part of
this initial foundation.

## Storefront email workflows

Customer signup sends a short-lived, rate-limited verification code to the
registration email. Frappe creates the Website User only after the code is
verified. Store orders record an expected delivery date seven calendar days
after placement and queue an email confirmation with the order items, total,
status, and expected date. Configure outgoing email on the Frappe site to
deliver these messages: add an **Email Account** in Frappe Desk with your
provider's SMTP settings, enable outgoing email, set it as **Default Outgoing**,
and send a test email before retrying signup. Keep SMTP credentials out of the
repository. Run `bench --site frappe.local migrate` after updating the app to
create the color/variant child tables and add the variant fields to existing
bag and order tables.
