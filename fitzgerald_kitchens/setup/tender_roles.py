# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.permissions import add_permission

TENDER_ROLES = ("Tender Manager", "Tender User")

# ERPNext doctypes the tender forms link to or price from; the tender doctypes carry their own
# permissions in their JSON
READ_DOCTYPES = ("Customer", "Item", "Item Group", "Item Price")


def ensure_tender_permissions():
	"""Give the tender roles read access to the ERPNext doctypes the tender forms use.

	Done in code rather than as a Custom DocPerm fixture: the first custom rule on a doctype replaces
	its standard rules, and add_permission copies those across first so other roles keep access.
	"""
	for role in TENDER_ROLES:
		if not frappe.db.exists("Role", role):
			continue
		for doctype in READ_DOCTYPES:
			if not frappe.db.exists(
				"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
			):
				add_permission(doctype, role, 0, "read")
