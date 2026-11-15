import frappe
from frappe import _
from frappe.model.document import Document


class TextileEmployee(Document):
	def validate(self):
		if self.user:
			user_type = frappe.db.get_value("User", self.user, "user_type")
			if user_type != "System User":
				frappe.throw(_("Employees must be linked to a System User account."))

		if self.user and frappe.db.exists(
			"Textile Employee",
			{"user": self.user, "name": ["!=", self.name or ""]},
		):
			frappe.throw(_("This system user is already linked to an employee."))

	def on_update(self):
		previous = self.get_doc_before_save()
		previous_user = previous.user if previous else None
		if previous_user and previous_user != self.user:
			self._set_employee_role(previous_user, enabled=False)
		if self.user:
			self._set_employee_role(
				self.user,
				enabled=self.employment_status != "Inactive",
			)

	def on_trash(self):
		if self.user:
			self._set_employee_role(self.user, enabled=False)

	def _set_employee_role(self, user_name, enabled):
		user = frappe.get_doc("User", user_name)
		has_employee_role = any(role.role == "Textile Employee" for role in user.roles)
		if has_employee_role == enabled:
			return

		if enabled:
			user.append("roles", {"role": "Textile Employee"})
		else:
			user.roles = [role for role in user.roles if role.role != "Textile Employee"]
		user.flags.ignore_permissions = True
		user.save()
