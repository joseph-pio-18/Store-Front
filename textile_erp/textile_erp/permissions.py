import frappe


MANAGER_ROLES = ("Textile Admin", "HR Manager", "System Manager")


def _is_manager(user):
	return any(role in frappe.get_roles(user) for role in MANAGER_ROLES)


def _employee_name(user):
	if user == "Administrator" or _is_manager(user):
		return None
	return frappe.db.get_value(
		"Textile Employee",
		{"user": user, "employment_status": ["!=", "Inactive"]},
		"name",
	)


def _own_record_condition(doctype, user):
	if user == "Administrator" or _is_manager(user):
		return None
	employee = _employee_name(user)
	if not employee:
		return "1=0"
	return f"`tab{doctype}`.`employee` = {frappe.db.escape(employee)}"


def employee_query(user):
	if _is_manager(user) or user == "Administrator":
		return None
	if not _employee_name(user):
		return "1=0"
	return f"`tabTextile Employee`.`user` = {frappe.db.escape(user)}"


def attendance_query(user):
	return _own_record_condition("Employee Attendance", user)


def leave_request_query(user):
	return _own_record_condition("Employee Leave Request", user)


def _can_access_employee_record(doc, user, ptype, allow_employee_write=False):
	if user == "Administrator" or _is_manager(user):
		return True

	employee = _employee_name(user)
	if not employee:
		return False

	if doc.doctype == "Textile Employee":
		return ptype == "read" and doc.user == user

	if doc.employee != employee:
		return False

	if ptype == "read":
		return True
	if ptype == "create":
		return not doc.employee or doc.employee == employee
	return allow_employee_write and ptype == "write" and doc.status == "Pending"


def employee_has_permission(doc, ptype, user):
	if doc is None:
		return None
	return _can_access_employee_record(doc, user, ptype)


def attendance_has_permission(doc, ptype, user):
	if doc is None:
		return None
	return _can_access_employee_record(doc, user, ptype)


def leave_request_has_permission(doc, ptype, user):
	if doc is None:
		return None
	return _can_access_employee_record(doc, user, ptype, allow_employee_write=True)
