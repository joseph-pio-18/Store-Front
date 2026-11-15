# Textile Storefront

React storefront for the Frappe `Textile Item` catalog. Only finished products
marked **Publish on Website** are returned by the guest API. The audience
category selector shows products for **Women**, **Men**, and **Kids** separately.
Product images come from each item's **Website Image** field, uploaded on its
Frappe record.

## Run locally

Start the `frappe.local` bench and install the `textile_erp` app first. Then:

```bash
npm install
npm run dev
```

The Vite development server proxies API and public file requests to
`http://127.0.0.1:8001` with the `frappe.local` host header.

## Customer accounts

Sign-in uses Frappe's native session and password endpoints. Registration
creates a Frappe **Website User**; passwords are handled by Frappe, and the
React app only keeps the session cookie managed by Frappe. Registration is
rate-limited.

To allow self-registration, sign in to Frappe Desk as an administrator, open
**Website Settings**, and clear **Disable Signup**. If signup remains disabled,
the storefront displays the server's registration error. Registration sends a
6-digit verification code to the entered email address; it expires after 10
minutes. The account is created only after the code is verified. New users can
then sign in with their registered email and password. Configure outgoing
email in Frappe so verification codes can be delivered.

Password-recovery workflows are not configured in this initial implementation.

The bag is stored in Frappe as one **Shopping Bag** per Website User, with
product IDs and quantities in **Shopping Bag Item** rows. Registration creates
an empty bag, and older accounts get one the first time they sign in. The
storefront fetches product images and current prices from the linked
**Textile Item** records. Quantity changes and removals are saved immediately.

Placing an order requires a signed-in Website User and creates a **Store Order**
record in Frappe with pending status. The bag is cleared only after Frappe
confirms the order. Frappe records an expected delivery date seven calendar
days after placement and emails the customer the order details and expected
date. The order total uses current server-side product prices; online payment
and inventory reservation are not implemented.
