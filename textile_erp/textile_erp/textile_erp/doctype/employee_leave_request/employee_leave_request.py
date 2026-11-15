import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


HR_ROLES = ("Textile Admin", "HR Manager", "System Manager")


class EmployeeLeaveRequest(Document):
	def validate(self):
		is_hr_manager = any(role in frappe.get_roles(frappe.session.user) for role in HR_ROLES)
		if not is_hr_manager:
			employee = frappe.db.get_value(
				"Textile Employee",
				{"user": frappe.session.user},
				"name",
			)
			if not employee:
				frappe.throw(_("Your user is not linked to an employee record."))
			if self.employee and self.employee != employee:
				frappe.throw(_("You can only request leave for yourself."))
			self.employee = employee
			if self.status != "Pending":
				frappe.throw(_("Only an HR Manager can approve or reject leave requests."))
			self.approved_by = None
			self.approval_date = None

		if self.from_date > self.to_date:
			frappe.throw(_("To Date cannot be earlier than From Date."))

		overlap = frappe.db.sql(
			"""
			SELECT name
			FROM `tabEmployee Leave Request`
			WHERE employee = %s
				AND name != %s
				AND status IN ('Pending', 'Approved')
				AND from_date <= %s
				AND to_date >= %s
			LIMIT 1
			""",
			(self.employee, self.name or "", self.to_date, self.from_date),
		)
		if overlap:
			frappe.throw(_("This leave request overlaps another pending or approved request."))

		if is_hr_manager:
			previous = self.get_doc_before_save()
			status_changed = not previous or previous.status != self.status
			if self.status in ("Approved", "Rejected") and status_changed:
				self.approved_by = frappe.session.user
				self.approval_date = now_datetime()
			elif self.status == "Pending" and status_changed:
				self.approved_by = None
				self.approval_date = None
