import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


def get_stock_balance(item_code):
	frappe.db.sql(
		"SELECT name FROM `tabTextile Item` WHERE name = %s FOR UPDATE",
		item_code,
	)
	movements = frappe.db.sql(
		"""
		SELECT movement_type, qty
		FROM `tabStock Movement`
		WHERE item = %s AND docstatus = 1
		FOR UPDATE
		""",
		item_code,
	)
	return flt(
		sum(qty if movement_type == "Receipt" else -qty for movement_type, qty in movements)
	)


class StockMovement(Document):
	def validate(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("Quantity must be greater than zero."))

		item = frappe.get_doc("Textile Item", self.item)
		if item.disabled:
			frappe.throw(_("Disabled items cannot be moved in stock."))

		if self.production_order and not frappe.flags.in_production_order:
			frappe.throw(_("Production Orders create their own stock movements."))

		if self.movement_type == "Issue" and get_stock_balance(self.item) < flt(self.qty):
			frappe.throw(_("Insufficient stock for {0}.").format(item.item_name))

	def before_cancel(self):
		if self.movement_type == "Receipt" and get_stock_balance(self.item) < flt(self.qty):
			item_name = frappe.db.get_value("Textile Item", self.item, "item_name")
			frappe.throw(
				_("Cannot cancel this receipt because {0} has already been consumed.").format(item_name)
			)
