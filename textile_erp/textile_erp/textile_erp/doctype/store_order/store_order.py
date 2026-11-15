import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, nowdate
from textile_erp.textile_erp.doctype.textile_item_variant.textile_item_variant import change_variant_stock


def get_expected_delivery_date(order_date):
	return add_days(order_date, 7)


class StoreOrder(Document):
	def before_insert(self):
		self.order_date = nowdate()
		self.expected_delivery_date = get_expected_delivery_date(self.order_date)

	def validate(self):
		previous = self.get_doc_before_save()
		if previous:
			if previous.status == "Cancelled" and self.status != "Cancelled":
				frappe.throw(_("A cancelled order cannot be reopened."))
			if previous.stock_reserved and self._order_items_snapshot() != self._order_items_snapshot(previous):
				frappe.throw(_("Order items cannot be changed while stock is reserved. Cancel the order instead."))

		if not self.items:
			frappe.throw(_("An order must contain at least one product."))

		total = 0
		for row in self.items:
			if flt(row.quantity) <= 0 or flt(row.rate) < 0:
				frappe.throw(_("Order quantities must be positive and prices cannot be negative."))
			row.amount = flt(row.quantity) * flt(row.rate)
			total += row.amount
		self.total_amount = total

	def on_update(self):
		previous = self.get_doc_before_save()
		if previous and previous.status != "Cancelled" and self.status == "Cancelled" and self.stock_reserved:
			for order_item in self.items:
				if not order_item.variant_id:
					continue
				change_variant_stock(
					order_item.variant_id,
					order_item.item_code,
					order_item.quantity,
					reserve=False,
				)
			self.db_set("stock_reserved", 0, update_modified=False)

	def on_trash(self):
		if self.stock_reserved:
			frappe.throw(_("Cancel this order to restore its reserved variant stock before deleting it."))

	@staticmethod
	def _order_items_snapshot(order):
		return sorted(
			(
				row.item_code,
				row.variant_id or "",
				row.color or "",
				row.size or "",
				row.quantity,
				row.rate,
			)
			for row in order.items
		)
