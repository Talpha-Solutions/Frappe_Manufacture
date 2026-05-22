import frappe

# ERPNext 16.8.x lists this patch but the module file was never shipped (see frappe/erpnext#53283).
_ERPNext_BROKEN_PATCH = "erpnext.patches.v11_1.rename_depends_on_lwp"


def before_migrate():
	"""Prepare site for migrate (ERPNext patch skip, fixture DocType imports)."""
	_enable_developer_mode_for_migrate()
	_skip_erpnext_broken_patch()


def after_migrate():
	"""Restore developer_mode if it was temporarily enabled for migrate."""
	if hasattr(frappe.flags, "_fitzgerald_restore_developer_mode"):
		frappe.conf.developer_mode = frappe.flags._fitzgerald_restore_developer_mode


def _enable_developer_mode_for_migrate():
	"""Fixture sync may import standard DocType JSON (e.g. aviation_mro); requires dev mode."""
	if frappe.conf.get("developer_mode"):
		return

	frappe.flags._fitzgerald_restore_developer_mode = 0
	frappe.conf.developer_mode = 1


def _skip_erpnext_broken_patch():
	if frappe.db.get_value("Patch Log", {"patch": _ERPNext_BROKEN_PATCH, "skipped": 0}):
		return

	frappe.get_doc({"doctype": "Patch Log", "patch": _ERPNext_BROKEN_PATCH}).insert(
		ignore_permissions=True
	)
	frappe.db.commit()