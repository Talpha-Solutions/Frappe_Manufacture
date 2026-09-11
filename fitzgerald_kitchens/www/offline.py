# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
import frappe.sessions
from frappe import _

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import is_item_enabled
from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.settings import generic_offline_allowed, get_configured_rows


def get_context(context):
	"""Web page controller for /offline — unified DocType + My Tasks PWA shell."""

	context.no_cache = 1

	if frappe.session.user == "Guest":
		frappe.throw(_("You need to be logged in to use the offline app."), frappe.PermissionError)

	generic_ok = generic_offline_allowed()
	my_tasks_ok = is_item_enabled("fk.my_tasks")

	if not (generic_ok or my_tasks_ok):
		frappe.throw(
			_(
				"Offline Sync is not ready. "
				"Open Offline Sync Settings, enable it, add DocTypes and/or the My Tasks pack "
				"(or click Apply Phase 1 Defaults), then save. "
				"Desk stays online-only — field work uses /offline."
			),
			frappe.PermissionError,
		)

	if "System Manager" not in frappe.get_roles():
		allowed = my_tasks_ok
		if not allowed:
			for row in get_configured_rows():
				if frappe.has_permission(row.ref_doctype, "read"):
					allowed = True
					break
		if not allowed:
			frappe.throw(
				_("You are not permitted to access any offline DocTypes or My Tasks."),
				frappe.PermissionError,
			)

	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
