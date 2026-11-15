import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


PRODUCT_CATEGORIES = ("Women", "Men", "Kids")


class TextileItem(Document):
	def validate(self):
		if self.item_type == "Raw Material":
			self.publish_on_website = 0
			self.selling_price = 0
		else:
			if flt(self.selling_price) < 0:
				frappe.throw(_("Selling Price cannot be negative."))
			if self.publish_on_website:
				if self.product_category not in PRODUCT_CATEGORIES:
					frappe.throw(_("Choose Women, Men, or Kids for a published product."))

		if self.publish_on_website and self.website_image and not self.website_image.startswith("/files/"):
			frappe.throw(_("Website images must use a public file upload from /files/."))

		colors_by_name = {}
		for color in self.colors:
			color.color = (color.color or "").strip()
			if not color.color:
				frappe.throw(_("Every color option must have a name."))
			color_key = color.color.casefold()
			if color_key in colors_by_name:
				frappe.throw(_("Color names must be unique for a product."))
			if color.image and not color.image.startswith("/files/"):
				frappe.throw(_("Color images must use a public file upload from /files/."))
			colors_by_name[color_key] = color

		variants_by_key = set()
		for variant in self.variants:
			variant.color = (variant.color or "").strip()
			variant.size = (variant.size or "").strip()
			if not variant.color or not variant.size:
				frappe.throw(_("Every size and color variant must specify both values."))
			if isinstance(variant.available_qty, bool) or int(variant.available_qty or 0) < 0:
				frappe.throw(_("Variant quantities cannot be negative."))
			if variant.color.casefold() not in colors_by_name:
				if self.publish_on_website:
					frappe.throw(_("Variant color {0} must be listed under Colors and Images.").format(variant.color))
				continue
			variant.color = colors_by_name[variant.color.casefold()].color
			variant_key = (variant.color.casefold(), variant.size.casefold())
			if variant_key in variants_by_key:
				frappe.throw(_("Each size and color combination must be unique."))
			variants_by_key.add(variant_key)

		if self.publish_on_website and bool(self.colors) != bool(self.variants):
			frappe.throw(_("Published products with color options must have at least one size and color quantity."))

		self._prevent_changing_reserved_variants()

	def _prevent_changing_reserved_variants(self):
		previous = self.get_doc_before_save()
		if not previous:
			return

		current_variants = {variant.name: variant for variant in self.variants if variant.name}
		for variant in previous.variants:
			current_variant = current_variants.get(variant.name)
			if current_variant and (variant.color, variant.size) == (
				current_variant.color,
				current_variant.size,
			):
				continue
			reserved = frappe.db.sql(
				"""
				SELECT soi.name
				FROM `tabStore Order Item` soi
				INNER JOIN `tabStore Order` so ON so.name = soi.parent
				WHERE soi.variant_id = %s AND soi.parenttype = 'Store Order' AND so.stock_reserved = 1
				LIMIT 1
				""",
				variant.name,
			)
			if reserved:
				frappe.throw(_("A size and color variant with reserved orders cannot be removed or renamed."))
