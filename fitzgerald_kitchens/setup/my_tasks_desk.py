# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.permissions import add_permission

MY_TASKS_ROLE = "My Tasks User"

DESKTOP_ICON_NAME = "My Tasks"

PERMISSIONS = [
	("Task", "read"),
	("Task", "write"),
	("ToDo", "read"),
	("Project", "read"),
	("Timesheet", "read"),
	("Timesheet", "write"),
	("Timesheet", "create"),
	("Timesheet", "submit"),
	("File", "read"),
	("File", "write"),
	("File", "create"),
	("Development Unit", "read"),
	("Development Unit QR Scan", "read"),
	("Development Unit QR Scan", "write"),
	("Development Unit QR Scan", "create"),
	("Task Label Scan Log", "read"),
	("Task Label Scan Log", "write"),
	("Task Label Scan Log", "create"),
]


def ensure_my_tasks_desk():
	"""Role, DocPerms, Pages, Desktop Icon visibility, and External icon permission patch."""
	ensure_my_tasks_role()
	_ensure_permissions()
	ensure_my_tasks_pages()
	ensure_my_tasks_desktop_icon()
	patch_desktop_icon_external_permission()


MY_TASKS_PAGE_NAMES = ("my-tasks", "task-scan")


def ensure_my_tasks_pages():
	"""Import desk pages from module JSON (works without developer_mode on Frappe Cloud)."""
	import os

	from frappe.modules.import_file import import_file_by_path

	app_path = frappe.get_app_path("fitzgerald_kitchens", "fitzgerald_kitchens")
	for page_name in MY_TASKS_PAGE_NAMES:
		folder = frappe.scrub(page_name)
		page_path = os.path.join(app_path, "page", folder, f"{folder}.json")
		if os.path.exists(page_path):
			import_file_by_path(page_path, force=True, reset_permissions=True)


def ensure_my_tasks_role():
	if frappe.db.exists("Role", MY_TASKS_ROLE):
		return

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": MY_TASKS_ROLE,
			"desk_access": 1,
		}
	).insert(ignore_permissions=True)


def _ensure_permissions():
	by_doctype: dict[str, set[str]] = {}
	for doctype, ptype in PERMISSIONS:
		by_doctype.setdefault(doctype, set()).add(ptype)

	for doctype, ptypes in by_doctype.items():
		perm_name = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": doctype, "role": MY_TASKS_ROLE, "permlevel": 0, "if_owner": 0},
			"name",
		)
		if perm_name:
			doc = frappe.get_doc("Custom DocPerm", perm_name)
			changed = False
			for ptype in ptypes:
				if not doc.get(ptype):
					doc.set(ptype, 1)
					changed = True
			if changed:
				doc.save(ignore_permissions=True)
			continue

		first = True
		for ptype in ptypes:
			if first:
				add_permission(doctype, MY_TASKS_ROLE, 0, ptype)
				first = False
			else:
				perm_name = frappe.db.get_value(
					"Custom DocPerm",
					{"parent": doctype, "role": MY_TASKS_ROLE, "permlevel": 0},
					"name",
				)
				if perm_name:
					doc = frappe.get_doc("Custom DocPerm", perm_name)
					doc.set(ptype, 1)
					doc.save(ignore_permissions=True)


def ensure_my_tasks_desktop_icon():
	"""Sync standard Desktop Icon from app desktop_icon JSON if missing."""
	if frappe.db.exists("Desktop Icon", DESKTOP_ICON_NAME):
		doc = frappe.get_doc("Desktop Icon", DESKTOP_ICON_NAME)
		needs_save = False
		if doc.link_type != "External" or doc.link != "/app/my-tasks":
			doc.link_type = "External"
			doc.link = "/app/my-tasks"
			needs_save = True
		if doc.hidden:
			doc.hidden = 0
			needs_save = True
		if needs_save:
			doc.save(ignore_permissions=True)
		return

	from frappe.modules.import_file import import_file_by_path
	import os

	app_path = frappe.get_app_path("fitzgerald_kitchens")
	icon_path = os.path.join(app_path, "desktop_icon", "my_tasks.json")
	if os.path.exists(icon_path):
		import_file_by_path(icon_path, force=True)
		clear_desktop_icons_cache()
		return

	# Fallback create
	doc = frappe.get_doc(
		{
			"doctype": "Desktop Icon",
			"name": DESKTOP_ICON_NAME,
			"label": DESKTOP_ICON_NAME,
			"link_type": "External",
			"link": "/app/my-tasks",
			"icon_type": "Link",
			"icon": "list-checks",
			"app": "fitzgerald_kitchens",
			"bg_color": "blue",
			"idx": 8,
			"standard": 1,
			"roles": [
				{"role": "My Tasks User"},
				{"role": "Projects User"},
				{"role": "Projects Manager"},
				{"role": "System Manager"},
			],
		}
	)
	doc.insert(ignore_permissions=True)
	clear_desktop_icons_cache()


def clear_desktop_icons_cache():
	from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache as _clear

	_clear()


def patch_desktop_icon_external_permission():
	"""Allow External Desktop Icons (My Tasks) without a Workspace Sidebar."""
	from frappe.desk.doctype.desktop_icon.desktop_icon import DesktopIcon

	if getattr(DesktopIcon, "_fk_my_tasks_icon_patched", False):
		return

	original = DesktopIcon.is_permitted

	def is_permitted(self, bootinfo):
		if self.link_type == "External" and self.link and self.link.startswith("/app/my-tasks"):
			allowed_roles = [d.role for d in self.get("roles") or []]
			if allowed_roles and not set(allowed_roles).intersection(frappe.get_roles()):
				return False
			return True
		return original(self, bootinfo)

	DesktopIcon.is_permitted = is_permitted
	DesktopIcon._fk_my_tasks_icon_patched = True
