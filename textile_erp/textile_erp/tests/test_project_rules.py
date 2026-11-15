import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch

import frappe
from textile_erp import hooks
from textile_erp.api import PUBLIC_PRODUCT_FIELDS
from textile_erp.api import _registration_otp_digest
from textile_erp.api import _validate_bag_items
from textile_erp.api import _validate_pagination
from textile_erp.api import _validate_registration_details
from textile_erp.api import _include_product_options
from textile_erp.api import place_store_order
from textile_erp.api import verify_customer_registration
from textile_erp.permissions import _is_manager
from textile_erp.textile_erp.doctype.textile_item_variant.textile_item_variant import change_variant_stock
from textile_erp.textile_erp.doctype.production_order.production_order import (
	get_required_material_quantity,
)
from textile_erp.textile_erp.doctype.store_order.store_order import StoreOrder
from textile_erp.textile_erp.doctype.store_order.store_order import get_expected_delivery_date


class TestProjectRules(unittest.TestCase):
	def test_material_quantity_scales_with_production_quantity(self):
		self.assertEqual(get_required_material_quantity(1.5, 8), 12)

	def test_material_quantity_preserves_fractional_amounts(self):
		self.assertEqual(get_required_material_quantity(0.125, 4), 0.5)

	def test_store_order_expected_delivery_is_seven_days_after_order_date(self):
		self.assertEqual(get_expected_delivery_date("2026-03-01"), "2026-03-08")

	def test_public_catalog_excludes_internal_stock_and_employee_data(self):
		self.assertNotIn("stock_balance", PUBLIC_PRODUCT_FIELDS)
		self.assertNotIn("employee", PUBLIC_PRODUCT_FIELDS)
		self.assertNotIn("user", PUBLIC_PRODUCT_FIELDS)

	def test_frappe_only_app_does_not_depend_on_erpnext(self):
		self.assertNotIn("erpnext", hooks.required_apps)

	def test_manager_role_check_uses_frappe_roles(self):
		with patch("textile_erp.permissions.frappe.get_roles", return_value=["HR Manager"]):
			self.assertTrue(_is_manager("hr@example.com"))
		with patch("textile_erp.permissions.frappe.get_roles", return_value=["Textile Employee"]):
			self.assertFalse(_is_manager("employee@example.com"))

	def test_catalog_pagination_rejects_out_of_range_values(self):
		self.assertEqual(_validate_pagination(20, 0), (20, 0))
		with patch("textile_erp.api._", side_effect=lambda message: message):
			with patch("textile_erp.api.frappe.throw", side_effect=frappe.ValidationError):
				with self.assertRaises(frappe.ValidationError):
					_validate_pagination(51, 0)
				with self.assertRaises(frappe.ValidationError):
					_validate_pagination(20, -1)

	def test_registration_details_normalize_email_and_validate_password(self):
		self.assertEqual(
			_validate_registration_details(
				" CUSTOMER@EXAMPLE.COM ",
				"Customer",
				"long-enough-password",
				"long-enough-password",
			),
			("customer@example.com", "Customer"),
		)

	def test_registration_rejects_mismatched_passwords(self):
		with patch("textile_erp.api._", side_effect=lambda message: message):
			with patch("textile_erp.api.frappe.throw", side_effect=frappe.ValidationError):
				with self.assertRaises(frappe.ValidationError):
					_validate_registration_details("customer@example.com", "Customer", "long-password", "different")

	def test_registration_otp_digest_reloads_missing_site_key(self):
		with patch("textile_erp.api.frappe.local.conf", {"encryption_key": None}):
			with patch(
				"textile_erp.api.frappe.get_site_config",
				return_value={"encryption_key": "site-secret"},
			):
				digest = _registration_otp_digest("customer@example.com", "123456")

		expected = hmac.new(
			b"site-secret",
			b"customer@example.com:123456",
			hashlib.sha256,
		).hexdigest()
		self.assertEqual(digest, expected)

	def test_registration_verification_creates_account_and_returns_message(self):
		challenge = {
			"full_name": "Customer",
			"otp_digest": "expected-digest",
			"attempts": 0,
			"expires_at": 2000,
		}
		cache = MagicMock()
		cache.get_value.return_value = challenge
		user = MagicMock()

		with patch("textile_erp.api.is_signup_disabled", return_value=False):
			with patch("textile_erp.api.frappe.cache", return_value=cache):
				with patch("textile_erp.api.time.time", return_value=1000):
					with patch("textile_erp.api._registration_otp_digest", return_value="expected-digest"):
						with patch("textile_erp.api._customer_account_exists", return_value=False):
							with patch("textile_erp.api.frappe.get_doc", return_value=user):
								with patch("textile_erp.api._get_or_create_customer_bag"):
									with patch("textile_erp.api._", side_effect=lambda message: message):
										result = verify_customer_registration(
											"customer@example.com",
											"123456",
											"Customer",
											"long-enough-password",
											"long-enough-password",
										)

		self.assertEqual(
			result,
			{"message": "Your email has been verified and your account has been created."},
		)
		user.insert.assert_called_once_with(ignore_permissions=True)

	def test_bag_items_use_product_id_and_qty(self):
		self.assertEqual(
			_validate_bag_items('[{"product_id": " DRESS-1 ", "qty": 2}]'),
			[{"product_id": "DRESS-1", "variant_id": None, "qty": 2}],
		)
		self.assertEqual(_validate_bag_items("[]"), [])

	def test_bag_items_allow_distinct_size_and_color_variants_of_one_product(self):
		self.assertEqual(
			_validate_bag_items(
				[
					{"product_id": "SHIRT-1", "variant_id": "variant-red-s", "qty": 2},
					{"product_id": "SHIRT-1", "variant_id": "variant-blue-m", "qty": 1},
				]
			),
			[
				{"product_id": "SHIRT-1", "variant_id": "variant-red-s", "qty": 2},
				{"product_id": "SHIRT-1", "variant_id": "variant-blue-m", "qty": 1},
			],
		)

	def test_public_products_include_color_images_and_variant_quantities(self):
		fake_frappe = MagicMock()
		fake_frappe.get_all.side_effect = [
			[frappe._dict(name="color-row", parent="SHIRT-1", color="Blue", image="/files/blue.jpg")],
			[
				frappe._dict(
					name="variant-row",
					parent="SHIRT-1",
					color="Blue",
					size="M",
					available_qty=3,
				)
			],
		]
		fake_frappe.db.get_default.return_value = "INR"
		with patch("textile_erp.api.frappe", fake_frappe):
			result = _include_product_options(
				[{"name": "SHIRT-1", "item_code": "SHIRT-1", "item_name": "Shirt"}]
			)

		self.assertEqual(result[0]["colors"], [{"color": "Blue", "image": "/files/blue.jpg"}])
		self.assertEqual(
			result[0]["variants"],
			[
				{
					"variant_id": "variant-row",
					"color": "Blue",
					"size": "M",
					"available_qty": 3,
				}
			],
		)
		self.assertEqual(result[0]["currency"], "INR")

	def test_variant_stock_reservation_uses_locked_current_quantity(self):
		fake_frappe = MagicMock()
		fake_frappe.db.sql.side_effect = [
			[frappe._dict(name="SHIRT-1", item_type="Finished Product", publish_on_website=1, disabled=0)],
			[
				frappe._dict(
					name="variant-row",
					parent="SHIRT-1",
					color="Blue",
					size="M",
					available_qty=4,
				)
			],
			None,
			None,
		]
		fake_frappe.session.user = "Administrator"
		with patch(
			"textile_erp.textile_erp.doctype.textile_item_variant.textile_item_variant.frappe",
			fake_frappe,
		):
			variant = change_variant_stock("variant-row", "SHIRT-1", 2, reserve=True)

		self.assertEqual(variant.available_qty, 2)
		self.assertEqual(fake_frappe.db.sql.call_count, 4)

	def test_order_placement_records_and_reserves_selected_variant(self):
		customer = frappe._dict(name="customer@example.com", full_name="Customer", email="customer@example.com")
		bag = MagicMock()
		bag.items = [frappe._dict(product_id="SHIRT-1", variant_id="variant-row", qty=2)]
		product = {
			"item_name": "Shirt",
			"selling_price": 25,
			"variants": [
				{
					"variant_id": "variant-row",
					"color": "Blue",
					"size": "M",
					"available_qty": 4,
				}
			],
		}
		order = MagicMock()
		order.name = "ORD-2026-00001"
		order.total_amount = 50
		order.currency = "INR"
		order.status = "Pending"
		order.expected_delivery_date = "2026-11-17"
		fake_frappe = MagicMock()
		fake_frappe.db.get_default.return_value = "INR"
		fake_frappe.get_doc.return_value = order

		with patch("textile_erp.api.frappe", fake_frappe):
			with patch("textile_erp.api._require_customer_user", return_value=customer):
				with patch("textile_erp.api._get_or_create_customer_bag", return_value=bag):
					with patch("textile_erp.api._get_available_bag_products", return_value={"SHIRT-1": product}):
						with patch(
							"textile_erp.api.change_variant_stock",
							return_value=frappe._dict(color="Blue", size="M", available_qty=2),
						) as reserve:
							with patch("textile_erp.api._send_order_confirmation"):
								result = place_store_order()

		reserve.assert_called_once_with("variant-row", "SHIRT-1", 2, reserve=True)
		order_doc = fake_frappe.get_doc.call_args.args[0]
		self.assertTrue(order_doc["stock_reserved"])
		self.assertEqual(order_doc["items"][0]["variant_id"], "variant-row")
		self.assertEqual(order_doc["items"][0]["color"], "Blue")
		self.assertEqual(order_doc["items"][0]["size"], "M")
		self.assertEqual(result["order_id"], "ORD-2026-00001")
		bag.set.assert_called_once_with("items", [])

	def test_cancelling_reserved_order_restores_variant_stock(self):
		order = MagicMock()
		order.status = "Cancelled"
		order.stock_reserved = 1
		order.items = [
			frappe._dict(item_code="SHIRT-1", variant_id="variant-row", quantity=2)
		]
		order.get_doc_before_save.return_value = frappe._dict(status="Pending")

		with patch(
			"textile_erp.textile_erp.doctype.store_order.store_order.change_variant_stock"
		) as restore:
			StoreOrder.on_update(order)

		restore.assert_called_once_with("variant-row", "SHIRT-1", 2, reserve=False)
		order.db_set.assert_called_once_with("stock_reserved", 0, update_modified=False)

	def test_bag_items_reject_duplicate_products_and_invalid_quantities(self):
		with patch("textile_erp.api._", side_effect=lambda message: message):
			with patch("textile_erp.api.frappe.throw", side_effect=frappe.ValidationError):
				with self.assertRaises(frappe.ValidationError):
					_validate_bag_items(
						[
							{"product_id": "DRESS-1", "qty": 1},
							{"product_id": " DRESS-1 ", "qty": 2},
						]
					)
				with self.assertRaises(frappe.ValidationError):
					_validate_bag_items(
						[
							{"product_id": "SHIRT-1", "variant_id": "red-small", "qty": 1},
							{"product_id": "SHIRT-1", "variant_id": "red-small", "qty": 2},
						]
					)
				for quantity in (0, 100, 1.5, True):
					with self.subTest(quantity=quantity):
						with self.assertRaises(frappe.ValidationError):
							_validate_bag_items([{"product_id": "DRESS-1", "qty": quantity}])


if __name__ == "__main__":
	unittest.main()
