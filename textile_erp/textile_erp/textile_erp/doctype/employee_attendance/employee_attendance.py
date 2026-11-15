import frappe
from frappe import _
from frappe.model.document import Document


HR_ROLES = ("Textile Admin", "HR Manager", "System Manager")


class EmployeeAttendance(Document):
	def validate(self):
		if not any(role in frappe.get_roles(frappe.session.user) for role in HR_ROLES):
			employee = frappe.db.get_value(
				"Textile Employee",
				{"user": frappe.session.user},
				"name",
			)
			if not employee:
				frappe.throw(_("Your user is not linked to an employee record."))
			if self.employee and self.employee != employee:
				frappe.throw(_("You can only create attendance for yourself."))
			self.employee = employee

		if frappe.db.exists(
			"Employee Attendance",
			{
				"employee": self.employee,
				"attendance_date": self.attendance_date,
				"name": ["!=", self.name or ""],
			},
		):
			frappe.throw(_("Attendance already exists for this employee and date."))
