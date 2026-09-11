# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
import frappe.sessions
from frappe import _

ALLOWED_ROLES = {"My Tasks User", "Projects User", "Projects Manager", "System Manager"}


def get_context(context):
	"""Web page controller for /offline_app — the offline-first PWA shell for
	field/production users. Not a Desk Page: this is a standalone route with
	its own manifest + service worker scope, so it can boot instantly while
	offline without needing Frappe Desk's full session/bootinfo pipeline.
	"""

	context.no_cache = 1

	if frappe.session.user == "Guest":
		frappe.throw(_("You need to be logged in to use the offline app."), frappe.PermissionError)

	from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import any_item_enabled_for_app

	if not any_item_enabled_for_app("fitzgerald_kitchens"):
		frappe.throw(
			_(
				"No Fitzgerald offline items are enabled. "
				"Open Offline Sync Settings, enable Offline Sync, add items such as "
				"My Tasks, Label Scan, or Development Units, and save."
			),
			frappe.PermissionError,
		)

	if not ALLOWED_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You are not permitted to access the offline app."), frappe.PermissionError)

	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
