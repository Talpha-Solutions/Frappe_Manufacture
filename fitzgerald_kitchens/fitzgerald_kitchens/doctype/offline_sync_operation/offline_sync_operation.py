# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OfflineSyncOperation(Document):
	def validate(self):
		if not self.user:
			self.user = frappe.session.user


def get_permission_query_conditions(user=None):
	"""Every consuming app shares this one ledger doctype, but a user should
	only ever see their own device's queued/processed operations."""
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return ""
	return f"(`tabOffline Sync Operation`.`user` = {frappe.db.escape(user)})"


def has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	return doc.user == user
