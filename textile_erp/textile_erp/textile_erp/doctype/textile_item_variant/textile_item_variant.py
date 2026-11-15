import frappe
from frappe import _
from frappe.model.document import Document


class TextileItemVariant(Document):
	pass


def change_variant_stock(variant_id, item_code, quantity, reserve):
	if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
		frappe.throw(_("Variant stock changes require a positive whole-number quantity."))

	products = frappe.db.sql(
		"""
		SELECT name, item_type, publish_on_website, disabled
		FROM `tabTextile Item`
		WHERE name = %s
		FOR UPDATE
		""",
		item_code,
		as_dict=True,
	)
	if not products or products[0].item_type != "Finished Product":
		frappe.throw(_("The selected product is no longer available."))
	if reserve and (not products[0].publish_on_website or products[0].disabled):
		frappe.throw(_("The selected product is no longer available."))
	rows = frappe.db.sql(
		"""
		SELECT name, parent, color, size, available_qty
		FROM `tabTextile Item Variant`
		WHERE name = %s AND parenttype = 'Textile Item' AND parentfield = 'variants'
		FOR UPDATE
		""",
		variant_id,
		as_dict=True,
	)
	if not rows or rows[0].parent != item_code:
		frappe.throw(_("The selected size and color are no longer available."))

	variant = rows[0]
	available_qty = int(variant.available_qty or 0)
	if reserve:
		if quantity > available_qty:
			frappe.throw(
				_("Only {0} of {1} in {2} remain. Update your bag and try again.").format(
					available_qty, variant.size, variant.color
				)
			)
		available_qty -= quantity
	else:
		available_qty += quantity

	frappe.db.sql(
		"""
		UPDATE `tabTextile Item Variant`
		SET available_qty = %s, modified = NOW(), modified_by = %s
		WHERE name = %s
		""",
		(available_qty, frappe.session.user, variant_id),
	)
	frappe.db.sql(
		"UPDATE `tabTextile Item` SET modified = NOW(), modified_by = %s WHERE name = %s",
		(frappe.session.user, item_code),
	)
	variant.available_qty = available_qty
	return variant
