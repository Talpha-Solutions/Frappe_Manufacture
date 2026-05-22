import frappe

# ERPNext 16.8.x lists this patch but the module file was never shipped (see frappe/erpnext#53283).
_ERPNext_BROKEN_PATCH = "erpnext.patches.v11_1.rename_depends_on_lwp"


def before_migrate():
	"""Skip ERPNext's missing rename_depends_on_lwp patch so migrate can proceed."""
	if frappe.db.get_value("Patch Log", {"patch": _ERPNext_BROKEN_PATCH, "skipped": 0}):
		return

	frappe.get_doc({"doctype": "Patch Log", "patch": _ERPNext_BROKEN_PATCH}).insert(
		ignore_permissions=True
	)
	frappe.db.commit()
