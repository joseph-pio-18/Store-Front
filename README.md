# Textile Manufacturing ERP

This project uses **Frappe Framework v15 only**; ERPNext is not installed in the
new bench. The custom backend app is in [`textile_erp/`](./textile_erp/), and
the React product storefront is in [`storefront/`](./storefront/).

## Start the Frappe site

The bench is under Ubuntu/WSL at `~/frappe-v15-bench`. In Ubuntu:

```bash
cd ~/frappe-v15-bench
bench new-site frappe.local
bench --site frappe.local install-app textile_erp
bench start
```

`bench new-site` prompts for local database and site administrator credentials.
The project does not store those credentials.
After updating an existing site, apply DocType changes with
`bench --site frappe.local migrate`.

## Frappe encryption key

Email verification stores a keyed digest of each registration code. Frappe must
have a Fernet-format `encryption_key` in the site configuration for this to
work. Generate one once from the bench directory if the key is missing or was
created in the wrong format:

```bash
cd ~/frappe-v15-bench
bench --site frappe.local set-config encryption_key "$(./env/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

Frappe requires a 32-byte URL-safe Base64 Fernet key; do not generate it with
`openssl rand -hex`. Do not replace an already-valid key, because doing so
prevents decrypting values stored with the previous key.

Restart the Frappe processes after changing configuration. For a local
development bench, stop the running `bench start` with **Ctrl+C** in its
terminal, then run `bench start` again; `bench restart` does not restart a
development bench. For production, use `bench restart`. Never commit or
replace the key; keep it in secure backups. If a key was previously configured
and then lost, restore the original key instead of generating a new one, since
a replacement cannot decrypt existing encrypted site values.

## Start the storefront

In a second terminal:

```bash
cd "/mnt/d/ERP Project/storefront"
npm install
npm run dev
```

Vite proxies `/api` and public `/files` requests to the Frappe site using the
`frappe.local` host header on port `8001`. Add finished garments in the custom
**Textile Item** DocType. Choose **Women**, **Men**, or **Kids** as the Audience
Category, upload a Website Image, enter the price, and mark the item **Publish
on Website**. The storefront loads those records from the Textile Item catalog
API and displays each audience category separately.

For apparel with options, add color names and one public image per color under
**Colors and Images**, then add a **Size and Color Stock** row for each
combination with its available quantity. Sizes accept standard labels such as
XS, S, M, L, XL, and XXL as well as custom labels. The storefront requires a
color and in-stock size before adding the item to the bag. Variant quantities
are reserved when an order is placed and restored if staff changes that order
to **Cancelled**. Existing products without variant rows remain single-option
items. These storefront variant quantities are maintained on the product;
the existing production stock ledger is still item-level and does not
automatically distribute production output across sizes or colors.

Customer registration uses Frappe Website User accounts and Frappe-managed
sessions. To enable it, in Frappe Desk open **Website Settings** and clear
**Disable Signup**. Registration sends a one-time email verification code that
expires after 10 minutes; verified customers can then sign in. Configure
outgoing email in Frappe for verification and order emails to be delivered.
The Frappe site must also have its `encryption_key` configured as described
above. In Frappe Desk, open **Email Account**, add an account using your
provider's SMTP server, port, TLS/SSL, login, and app password, enable outgoing
email, and set it as **Default Outgoing**. Use the provider's app password or
SMTP credential; do not put email credentials in this repository. Send a test
email from the Email Account form before retrying registration.
Passwords are never stored in the React app beyond the active registration
form and are submitted to Frappe only when the code is verified.

## Current foundation

- Raw and finished textile items with a stock unit and public product details.
- Material formulas and production orders that issue raw material and receive
  finished goods through a submitted stock ledger.
- Employee and department records, attendance, and leave requests with
  employee-scoped access, automatic employee-role assignment, and HR Manager
  approval.
- Public product catalog endpoints and a responsive React storefront with
  search, category filters, product details, and a quantity-editable bag.
- **Store Order** records for customer order requests, with **Store Order Item**
  child rows; orders are pending until staff process them. Each order records
  an expected delivery date seven calendar days after placement, and an email
  confirmation includes the order details and expected date. Online payment
  and stock reservation are not implemented.
- Customer bags persist in one **Shopping Bag** per Website User, with products
  and quantities stored in **Shopping Bag Item** child rows.

Payroll, recruitment, and country-specific HR/payroll rules are not implemented
yet.
