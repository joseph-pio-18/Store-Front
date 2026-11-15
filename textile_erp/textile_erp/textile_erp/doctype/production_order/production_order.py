import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


def get_required_material_quantity(qty_per_finished_unit, production_quantity):
	return flt(qty_per_finished_unit) * flt(production_quantity)


class ProductionOrder(Document):
	def validate(self):
		if flt(self.qty_to_produce) <= 0:
			frappe.throw(_("Quantity to Produce must be greater than zero."))

		product = frappe.get_doc("Textile Item", self.finished_product)
		if product.item_type != "Finished Product" or product.disabled:
			frappe.throw(_("Select an active Finished Product."))

		formula = frappe.get_doc("Material Formula", self.material_formula)
		if (
			formula.finished_product != self.finished_product
			or not formula.is_active
			or formula.docstatus != 1
		):
			frappe.throw(_("Select an active, submitted formula for this finished product."))

	def on_submit(self):
		formula = frappe.get_doc("Material Formula", self.material_formula)
		item_codes = sorted({row.item_code for row in formula.materials} | {self.finished_product})
		for item_code in item_codes:
			frappe.db.sql(
				"SELECT name FROM `tabTextile Item` WHERE name = %s FOR UPDATE",
				item_code,
			)

		frappe.flags.in_production_order = True
		try:
			for row in formula.materials:
				movement = frappe.get_doc(
					{
						"doctype": "Stock Movement",
						"item": row.item_code,
						"movement_type": "Issue",
						"qty": get_required_material_quantity(row.qty, self.qty_to_produce),
						"production_order": self.name,
						"reference": self.name,
						"notes": _("Consumed for production."),
					}
				)
				movement.insert(ignore_permissions=True)
				movement.submit()

			receipt = frappe.get_doc(
				{
					"doctype": "Stock Movement",
					"item": self.finished_product,
					"movement_type": "Receipt",
					"qty": self.qty_to_produce,
					"production_order": self.name,
					"reference": self.name,
					"notes": _("Finished goods from production."),
				}
			)
			receipt.insert(ignore_permissions=True)
			receipt.submit()
		finally:
			frappe.flags.in_production_order = False

		self.db_set("status", "Completed", update_modified=False)

	def on_cancel(self):
		movements = frappe.get_all(
			"Stock Movement",
			filters={"production_order": self.name, "docstatus": 1},
			pluck="name",
		)
		frappe.flags.in_production_order = True
		try:
			for movement_name in movements:
				frappe.get_doc("Stock Movement", movement_name).cancel()
		finally:
			frappe.flags.in_production_order = False
		self.db_set("status", "Cancelled", update_modified=False)
