# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe


def after_install():
	"""Ensure Desk launcher entry for the /offline PWA exists."""
	_ensure_desktop_icon()


def after_migrate():
	_ensure_desktop_icon()


def _ensure_desktop_icon():
	if frappe.db.exists("Desktop Icon", "Offline Sync"):
		return

	try:
		doc = frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": "Offline Sync",
				"app": "fitzgerald_kitchens",
				"icon_type": "Link",
				"link_type": "External",
				"link": "/offline",
				"icon": "cloud-off",
				"bg_color": "blue",
				"standard": 1,
				"hidden": 0,
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="offline_sync desktop icon setup")
