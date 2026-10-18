# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.permissions import add_permission, update_permission_property

TENDER_ROLES = ("Tender Manager", "Tender User")

# ERPNext doctypes the tender forms link to or price from; the tender doctypes carry their own
# permissions in their JSON
READ_DOCTYPES = ("Customer", "Item", "Item Group", "Item Price")
# a tender from someone we haven't worked with starts as a Lead, so the tender roles add and edit them
EDIT_DOCTYPES = ("Lead",)
# creating a won tender's projects converts its Lead to a Customer
MANAGER_CREATE_DOCTYPES = ("Customer",)


def ensure_tender_permissions():
	"""Give the tender roles access to the ERPNext doctypes the tender forms use: read, and for Lead edit.

	Done in code rather than as a Custom DocPerm fixture: the first custom rule on a doctype replaces
	its standard rules, and add_permission copies those across first so other roles keep access.
	"""
	for role in TENDER_ROLES:
		if not frappe.db.exists("Role", role):
			continue
		for doctype in READ_DOCTYPES + EDIT_DOCTYPES:
			if frappe.db.exists(
				"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
			):
				continue
			add_permission(doctype, role, 0, "read")
			if doctype in EDIT_DOCTYPES:
				for ptype in ("write", "create"):
					update_permission_property(doctype, role, 0, ptype, 1)

	if frappe.db.exists("Role", "Tender Manager"):
		for doctype in MANAGER_CREATE_DOCTYPES:
			if not frappe.db.get_value(
				"Custom DocPerm", {"parent": doctype, "role": "Tender Manager", "permlevel": 0, "if_owner": 0}, "create"
			):
				update_permission_property(doctype, "Tender Manager", 0, "create", 1)
