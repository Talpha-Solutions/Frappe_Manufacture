# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
import frappe.sessions
from frappe import _

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import is_item_enabled


def get_context(context):
	"""Offline fallback shell for Desk My Tasks when full Desk HTML is not cached."""
	context.no_cache = 1

	if frappe.session.user == "Guest":
		frappe.throw(_("You need to be logged in to use My Tasks offline."), frappe.PermissionError)

	if not is_item_enabled("fk.my_tasks"):
		frappe.throw(
			_("Enable the My Tasks offline pack in Offline Sync Settings."),
			frappe.PermissionError,
		)

	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
