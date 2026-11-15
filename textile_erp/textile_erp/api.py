import hashlib
import hmac
import json
import secrets
import time

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.sessions import get_csrf_token as get_session_csrf_token
from frappe.utils import add_days, getdate, nowdate
from frappe.utils.data import escape_html
from frappe.website.utils import is_signup_disabled
from textile_erp.textile_erp.doctype.textile_item_variant.textile_item_variant import change_variant_stock


PUBLIC_PRODUCT_FIELDS = (
	"name",
	"item_code",
	"item_name",
	"product_category",
	"selling_price",
	"stock_uom",
	"website_image",
	"website_description",
)
PRODUCT_CATEGORIES = ("Women", "Men", "Kids")
REGISTRATION_OTP_TTL = 10 * 60
REGISTRATION_OTP_MAX_ATTEMPTS = 5
REGISTRATION_OTP_RESEND_DELAY = 60


def _validate_pagination(limit, start):
	try:
		page_size = int(limit)
		offset = int(start)
	except (TypeError, ValueError):
		frappe.throw(_("Pagination values must be integers."))

	if page_size < 1 or page_size > 50:
		frappe.throw(_("Page size must be between 1 and 50."))
	if offset < 0:
		frappe.throw(_("Offset cannot be negative."))
	return page_size, offset


def _include_product_options(products):
	products = [{**product, "colors": [], "variants": []} for product in products]
	if not products:
		return products

	product_by_name = {product["name"]: product for product in products}
	product_names = list(product_by_name)
	colors = frappe.get_all(
		"Textile Item Color",
		filters={"parent": ["in", product_names], "parenttype": "Textile Item", "parentfield": "colors"},
		fields=["name", "parent", "color", "image", "idx"],
		order_by="parent asc, idx asc",
	)
	variants = frappe.get_all(
		"Textile Item Variant",
		filters={"parent": ["in", product_names], "parenttype": "Textile Item", "parentfield": "variants"},
		fields=["name", "parent", "color", "size", "available_qty", "idx"],
		order_by="parent asc, idx asc",
	)
	for color in colors:
		product_by_name[color.parent]["colors"].append(
			{"color": color.color, "image": color.image}
		)
	for variant in variants:
		product_by_name[variant.parent]["variants"].append(
			{
				"variant_id": variant.name,
				"color": variant.color,
				"size": variant.size,
				"available_qty": variant.available_qty,
			}
		)

	currency = frappe.db.get_default("currency")
	return [{**product, "currency": currency} for product in products]


@frappe.whitelist(allow_guest=True)
def get_products(search=None, category=None, limit=24, start=0):
	page_size, offset = _validate_pagination(limit, start)
	filters = {
		"item_type": "Finished Product",
		"publish_on_website": 1,
		"disabled": 0,
	}
	if category:
		if category not in PRODUCT_CATEGORIES:
			frappe.throw(_("Choose Women, Men, or Kids as the product category."))
		filters["product_category"] = category
	or_filters = None

	if search:
		search = str(search).strip()
		if len(search) > 100:
			frappe.throw(_("Search text cannot exceed 100 characters."))
		if search:
			like = f"%{search}%"
			or_filters = [
				{"item_code": ["like", like]},
				{"item_name": ["like", like]},
				{"product_category": ["like", like]},
			]

	query = {
		"filters": filters,
		"fields": PUBLIC_PRODUCT_FIELDS,
		"order_by": "item_name asc",
		"limit_start": offset,
		"limit_page_length": page_size,
	}
	if or_filters:
		query["or_filters"] = or_filters

	return _include_product_options(
		frappe.get_all(
			"Textile Item",
			**query,
		)
	)


@frappe.whitelist(allow_guest=True)
def get_product(item_code):
	if not item_code:
		frappe.throw(_("An item code is required."))

	product = frappe.get_all(
		"Textile Item",
		filters={
			"item_code": item_code,
			"item_type": "Finished Product",
			"publish_on_website": 1,
			"disabled": 0,
		},
		fields=PUBLIC_PRODUCT_FIELDS,
		limit_page_length=1,
	)
	if not product:
		frappe.throw(_("Product not found."), frappe.DoesNotExistError)
	return _include_product_options(product)[0]


def _require_customer_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in with a customer account to use your shopping bag."), frappe.PermissionError)

	customer = frappe.get_cached_doc("User", frappe.session.user)
	if customer.user_type != "Website User" or not customer.enabled:
		frappe.throw(_("Only active customer accounts can use the storefront bag."), frappe.PermissionError)
	return customer


def _get_or_create_customer_bag(customer):
	frappe.db.sql("SELECT name FROM `tabUser` WHERE name = %s FOR UPDATE", customer.name)
	bag_name = frappe.db.get_value("Shopping Bag", {"user": customer.name}, "name")
	if bag_name:
		return frappe.get_doc("Shopping Bag", bag_name)

	bag = frappe.get_doc({"doctype": "Shopping Bag", "user": customer.name})
	bag.insert(ignore_permissions=True)
	return bag


def _get_available_bag_products(bag, item_codes=None):
	item_codes = item_codes if item_codes is not None else [row.product_id for row in bag.items]
	if not item_codes:
		return {}

	products = frappe.get_all(
		"Textile Item",
		filters={
			"name": ["in", item_codes],
			"item_type": "Finished Product",
			"publish_on_website": 1,
			"disabled": 0,
		},
		fields=PUBLIC_PRODUCT_FIELDS,
	)
	return {product["item_code"]: product for product in _include_product_options(products)}


@frappe.whitelist()
def get_customer_bag():
	customer = _require_customer_user()
	bag = _get_or_create_customer_bag(customer)
	products = _get_available_bag_products(bag)
	return [
		{
			"product_id": row.product_id,
			"variant_id": row.variant_id or None,
			"color": row.color or None,
			"size": row.size or None,
			"qty": row.qty,
			"product": products.get(row.product_id),
		}
		for row in bag.items
	]


def _validate_bag_items(items):
	try:
		bag_items = json.loads(items) if isinstance(items, str) else items
	except (TypeError, ValueError):
		frappe.throw(_("Shopping bag items must be valid JSON."))

	if not isinstance(bag_items, list) or len(bag_items) > 50:
		frappe.throw(_("A shopping bag can contain up to 50 products."))

	validated_items = []
	seen_lines = set()
	for row in bag_items:
		if not isinstance(row, dict):
			frappe.throw(_("Each bag item must be an object."))
		product_id = row.get("product_id")
		variant_id = row.get("variant_id")
		qty = row.get("qty")
		if not isinstance(product_id, str) or not product_id.strip():
			frappe.throw(_("Each bag item must have a product ID."))
		product_id = product_id.strip()
		if variant_id is not None and not isinstance(variant_id, str):
			frappe.throw(_("Shopping bag variant IDs must be text values."))
		variant_id = variant_id.strip() if variant_id else None
		line_key = (product_id, variant_id)
		if line_key in seen_lines:
			frappe.throw(_("Each product size and color combination can only appear once in the shopping bag."))
		if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 99:
			frappe.throw(_("Product quantities must be whole numbers between 1 and 99."))
		seen_lines.add(line_key)
		validated_items.append({"product_id": product_id, "variant_id": variant_id, "qty": qty})
	return validated_items


@frappe.whitelist(methods=["POST"])
def update_customer_bag(items):
	customer = _require_customer_user()
	bag_items = _validate_bag_items(items)
	bag = _get_or_create_customer_bag(customer)
	products = _get_available_bag_products(bag, list({row["product_id"] for row in bag_items}))

	for row in bag_items:
		product = products.get(row["product_id"])
		if not product:
			frappe.throw(_("Product {0} is no longer available. Refresh the collection before adding it.").format(row["product_id"]))
		if product["variants"]:
			variant = next(
				(item for item in product["variants"] if item["variant_id"] == row["variant_id"]),
				None,
			)
			if not variant:
				frappe.throw(_("Choose a valid size and color for {0}.").format(product["item_name"]))
			if row["qty"] > variant["available_qty"]:
				frappe.throw(
					_("Only {0} of {1} in {2} are currently available.").format(
						variant["available_qty"], variant["size"], variant["color"]
					)
				)
			row["color"] = variant["color"]
			row["size"] = variant["size"]
		elif row["variant_id"]:
			frappe.throw(_("This product no longer has the selected size and color option."))
		else:
			row["color"] = None
			row["size"] = None

	bag.set("items", [])
	for row in bag_items:
		bag.append("items", row)
	bag.save(ignore_permissions=True)
	return get_customer_bag()


@frappe.whitelist(methods=["POST"])
def place_store_order():
	customer = _require_customer_user()
	bag = _get_or_create_customer_bag(customer)
	if not bag.items:
		frappe.throw(_("Your shopping bag is empty."))

	frappe.db.sql("SELECT name FROM `tabShopping Bag` WHERE name = %s FOR UPDATE", bag.name)
	item_codes = sorted({row.product_id for row in bag.items})
	for item_code in item_codes:
		frappe.db.sql("SELECT name FROM `tabTextile Item` WHERE name = %s FOR UPDATE", item_code)

	products = _get_available_bag_products(bag)
	if len(products) != len({row.product_id for row in bag.items}):
		unavailable = [row.product_id for row in bag.items if row.product_id not in products]
		frappe.throw(
			_("These products are no longer available: {0}. Remove them from your bag and try again.").format(
				", ".join(unavailable)
			)
		)

	order_rows = []
	reserves_variant_stock = False
	for row in bag.items:
		product = products[row.product_id]
		variant = None
		if product["variants"]:
			variant = next(
				(item for item in product["variants"] if item["variant_id"] == row.variant_id),
				None,
			)
			if not variant:
				frappe.throw(_("A size and color selection is required for {0}.").format(product["item_name"]))
			variant = change_variant_stock(row.variant_id, row.product_id, row.qty, reserve=True)
			if row.color != variant.color or row.size != variant.size:
				frappe.throw(_("A product option changed after you added it to your bag. Refresh the product and try again."))
			reserves_variant_stock = True
		elif row.variant_id:
			frappe.throw(_("The selected size and color are no longer available."))

		order_rows.append(
			{
				"item_code": row.product_id,
				"item_name": product["item_name"],
				"variant_id": row.variant_id if variant else None,
				"color": variant["color"] if variant else None,
				"size": variant["size"] if variant else None,
				"quantity": row.qty,
				"rate": product["selling_price"],
			}
		)

	order = frappe.get_doc(
		{
			"doctype": "Store Order",
			"customer": customer.name,
			"customer_name": customer.full_name,
			"customer_email": customer.email,
			"currency": frappe.db.get_default("currency"),
			"stock_reserved": reserves_variant_stock,
			"items": order_rows,
		}
	)
	order.insert(ignore_permissions=True)
	_send_order_confirmation(order)
	bag.set("items", [])
	bag.save(ignore_permissions=True)

	return {
		"order_id": order.name,
		"total_amount": order.total_amount,
		"currency": order.currency,
		"status": order.status,
		"expected_delivery_date": str(order.expected_delivery_date),
	}


@frappe.whitelist(allow_guest=True)
def get_csrf_token():
	return get_session_csrf_token()


def _validate_registration_details(email, full_name, password=None, confirm_password=None):
	email = (email or "").strip().lower()
	full_name = (full_name or "").strip()
	if not email or len(email) > 140 or "@" not in email:
		frappe.throw(_("Enter a valid email address."))
	if not full_name or len(full_name) > 140:
		frappe.throw(_("Enter a name between 1 and 140 characters."))
	if password is not None:
		if len(password) < 10:
			frappe.throw(_("Password must be at least 10 characters long."))
		if len(password) > 128:
			frappe.throw(_("Password cannot exceed 128 characters."))
		if password != confirm_password:
			frappe.throw(_("Passwords do not match."))
	return email, full_name


def _registration_otp_key(email):
	return "textile_erp:registration_otp:" + hashlib.sha256(email.encode()).hexdigest()


def _registration_otp_digest(email, otp):
	encryption_key = frappe.local.conf.get("encryption_key")
	if not encryption_key:
		encryption_key = frappe.get_site_config().get("encryption_key")
	if not encryption_key:
		frappe.throw(
			_("Email verification is unavailable because site encryption is not configured. "
			  "Ask the site administrator to configure the Frappe encryption key.")
		)
	return hmac.new(
		encryption_key.encode(),
		f"{email}:{otp}".encode(),
		hashlib.sha256,
	).hexdigest()


def _customer_account_exists(email):
	return bool(
		frappe.db.exists("User", email)
		or frappe.db.exists("User", {"email": email})
	)


def _send_order_confirmation(order):
	item_lines = []
	for item in order.items:
		variant_label = ""
		if item.color or item.size:
			option_labels = [
				escape_html(value) for value in (item.color, item.size) if value
			]
			variant_label = f"<br><small>{', '.join(option_labels)}</small>"
		item_lines.append(
			"<tr>"
			f"<td>{escape_html(item.item_name)}{variant_label}</td>"
			f"<td>{item.quantity}</td>"
			f"<td>{escape_html(order.currency)} {item.rate:,.2f}</td>"
			f"<td>{escape_html(order.currency)} {item.amount:,.2f}</td>"
			"</tr>"
		)
	expected_date = getdate(order.expected_delivery_date).strftime("%d %b %Y")
	order_date = getdate(order.order_date).strftime("%d %b %Y")
	message = (
		f"<p>Thank you for your order, {escape_html(order.customer_name)}.</p>"
		f"<p><strong>Order:</strong> {escape_html(order.name)}<br>"
		f"<strong>Order date:</strong> {order_date}<br>"
		f"<strong>Expected delivery:</strong> {expected_date}<br>"
		f"<strong>Status:</strong> {escape_html(order.status)}</p>"
		"<table border='1' cellpadding='6' cellspacing='0'>"
		"<thead><tr><th>Product</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr></thead>"
		f"<tbody>{''.join(item_lines)}</tbody></table>"
		f"<p><strong>Total:</strong> {escape_html(order.currency)} {order.total_amount:,.2f}</p>"
		"<p>We will contact you if there are updates to your order.</p>"
	)
	frappe.sendmail(
		recipients=[order.customer_email],
		subject=_("Order {0} confirmation").format(order.name),
		message=message,
		reference_doctype="Store Order",
		reference_name=order.name,
		delayed=True,
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60, methods=["POST"])
def start_customer_registration(email, full_name):
	if is_signup_disabled():
		frappe.throw(_("Customer registration is currently disabled."))

	email, full_name = _validate_registration_details(email, full_name)
	if _customer_account_exists(email):
		return {
			"account_exists": True,
			"message": _("An account with this email already exists. Please sign in instead."),
		}

	cache = frappe.cache()
	otp_key = _registration_otp_key(email)
	cooldown_key = f"{otp_key}:cooldown"
	if cache.get_value(cooldown_key):
		frappe.throw(_("Please wait a minute before requesting another verification code."))

	otp = f"{secrets.randbelow(1_000_000):06d}"
	cache.set_value(
		otp_key,
		{
			"full_name": full_name,
			"otp_digest": _registration_otp_digest(email, otp),
			"attempts": 0,
			"expires_at": time.time() + REGISTRATION_OTP_TTL,
		},
		expires_in_sec=REGISTRATION_OTP_TTL,
	)
	try:
		frappe.sendmail(
			recipients=[email],
			subject=_("Verify your Threadform email"),
			message=(
				f"<p>Hello {escape_html(full_name)},</p>"
				f"<p>Your email verification code is <strong>{otp}</strong>.</p>"
				"<p>This code expires in 10 minutes. If you did not request it, you can ignore this email.</p>"
			),
			delayed=True,
		)
	except frappe.OutgoingEmailError:
		cache.delete_value(otp_key)
		frappe.log_error(frappe.get_traceback(), _("Customer registration OTP email failed"))
		frappe.throw(
			_(
				"Email verification is unavailable because no default outgoing Email Account is configured. "
				"Configure an outgoing Email Account in Frappe Desk and mark it as Default Outgoing."
			)
		)
	except Exception:
		cache.delete_value(otp_key)
		frappe.log_error(frappe.get_traceback(), _("Customer registration OTP email failed"))
		frappe.throw(_("We could not send the verification email. Please try again later."))
	cache.set_value(cooldown_key, "1", expires_in_sec=REGISTRATION_OTP_RESEND_DELAY)
	return {
		"account_exists": False,
		"message": _("A verification code has been sent to your email address."),
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60, methods=["POST"])
def verify_customer_registration(email, otp, full_name, password, confirm_password):
	if is_signup_disabled():
		frappe.throw(_("Customer registration is currently disabled."))

	email = _validate_registration_details(email, full_name, password, confirm_password)[0]
	if not isinstance(otp, str) or len(otp) != 6 or not otp.isdigit():
		frappe.throw(_("Enter the 6-digit verification code from your email."))

	cache = frappe.cache()
	otp_key = _registration_otp_key(email)
	challenge = cache.get_value(otp_key)
	if not challenge:
		frappe.throw(_("The verification code expired. Request a new code and try again."))
	remaining_ttl = int(challenge["expires_at"] - time.time())
	if remaining_ttl <= 0:
		cache.delete_value(otp_key)
		frappe.throw(_("The verification code expired. Request a new code and try again."))
	if challenge["attempts"] >= REGISTRATION_OTP_MAX_ATTEMPTS:
		cache.delete_value(otp_key)
		frappe.throw(_("Too many incorrect codes. Request a new verification code."))
	if not hmac.compare_digest(challenge["otp_digest"], _registration_otp_digest(email, otp)):
		challenge["attempts"] += 1
		cache.set_value(otp_key, challenge, expires_in_sec=remaining_ttl)
		if challenge["attempts"] >= REGISTRATION_OTP_MAX_ATTEMPTS:
			cache.delete_value(otp_key)
			frappe.throw(_("Too many incorrect codes. Request a new verification code."))
		frappe.throw(_("The verification code is incorrect."))

	if _customer_account_exists(email):
		cache.delete_value(otp_key)
		frappe.throw(_("An account with this email already exists. Please sign in instead."))

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": escape_html(challenge["full_name"]),
			"enabled": 1,
			"user_type": "Website User",
			"new_password": password,
			"send_welcome_email": 0,
		}
	)
	user.flags.ignore_permissions = True
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)
	_get_or_create_customer_bag(user)
	cache.delete_value(otp_key)
	cache.delete_value(f"{otp_key}:cooldown")

	return {"message": _("Your email has been verified and your account has been created.")}


@frappe.whitelist(allow_guest=True)
def get_customer_session():
	if frappe.session.user == "Guest":
		return None

	user = frappe.get_cached_doc("User", frappe.session.user)
	return {
		"email": user.name,
		"full_name": user.full_name,
		"user_type": user.user_type,
	}
