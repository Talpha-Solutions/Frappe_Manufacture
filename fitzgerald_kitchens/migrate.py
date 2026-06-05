import frappe
from frappe.installer import update_site_config

# ERPNext 16.8.x lists this patch but the module file was never shipped (see frappe/erpnext#53283).
_ERPNext_BROKEN_PATCH = "erpnext.patches.v11_1.rename_depends_on_lwp"


def before_migrate():
	"""Prepare site for migrate (ERPNext patch skip, fixture DocType imports)."""
	_enable_developer_mode_for_migrate()
	_skip_erpnext_broken_patch()


def after_migrate():
	"""Sync sidebar items and restore developer_mode after migrate."""
	from fitzgerald_kitchens.setup.workspace_sidebar import ensure_projects_sidebar

	ensure_projects_sidebar()

	if not hasattr(frappe.flags, "_fitzgerald_restore_developer_mode"):
		return

	update_site_config("developer_mode", frappe.flags._fitzgerald_restore_developer_mode)
	frappe.conf.developer_mode = frappe.flags._fitzgerald_restore_developer_mode


def _enable_developer_mode_for_migrate():
	"""Fixture sync imports standard DocType JSON; requires dev mode on disk.

	Setting only frappe.conf is not enough: model sync calls clear_cache() and reloads
	site_config, which would drop an in-memory override before sync_fixtures runs.
	"""
	if frappe.conf.get("developer_mode"):
		return

	frappe.flags._fitzgerald_restore_developer_mode = 0
	update_site_config("developer_mode", 1)
	frappe.conf.developer_mode = 1


def _skip_erpnext_broken_patch(): 
	if frappe.db.get_value("Patch Log", {"patch": _ERPNext_BROKEN_PATCH, "skipped": 0}):
		return

	frappe.get_doc({"doctype": "Patch Log", "patch": _ERPNext_BROKEN_PATCH}).insert(
		ignore_permissions=True
	)
	frappe.db.commit()