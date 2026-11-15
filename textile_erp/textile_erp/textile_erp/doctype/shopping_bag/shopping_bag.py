import frappe
from frappe import _
from frappe.model.document import Document


class ShoppingBag(Document):
	def validate(self):
		if not self.user or frappe.db.get_value("User", self.user, "user_type") != "Website User":
			frappe.throw(_("A shopping bag must belong to a Website User."))

		seen_lines = set()
		for row in self.items:
			line_key = (row.product_id, row.variant_id or None)
			if line_key in seen_lines:
				frappe.throw(_("Each product size and color combination can only appear once in a shopping bag."))
			seen_lines.add(line_key)
			if isinstance(row.qty, bool) or not isinstance(row.qty, int) or not 1 <= row.qty <= 99:
				frappe.throw(_("Product quantities must be whole numbers between 1 and 99."))
