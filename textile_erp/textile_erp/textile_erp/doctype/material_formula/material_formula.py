import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaterialFormula(Document):
	def validate(self):
		product = frappe.get_doc("Textile Item", self.finished_product)
		if product.item_type != "Finished Product" or product.disabled:
			frappe.throw(_("Select an active Finished Product."))

		seen_materials = set()
		if not self.materials:
			frappe.throw(_("Add at least one raw material."))

		for row in self.materials:
			if row.item_code in seen_materials:
				frappe.throw(_("Each raw material can appear only once."))
			seen_materials.add(row.item_code)

			item = frappe.get_doc("Textile Item", row.item_code)
			if item.item_type != "Raw Material" or item.disabled:
				frappe.throw(_("Formula materials must be active Raw Material items."))
			if flt(row.qty) <= 0:
				frappe.throw(_("Material quantities must be greater than zero."))

	def before_submit(self):
		if not self.is_active:
			frappe.throw(_("Only active formulas can be submitted."))

	def on_cancel(self):
		if frappe.db.exists(
			"Production Order",
			{"material_formula": self.name, "docstatus": 1},
		):
			frappe.throw(_("Cancel linked Production Orders before cancelling this formula."))
