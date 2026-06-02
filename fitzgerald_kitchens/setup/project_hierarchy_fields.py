# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

PARENT_PROJECT_FIELD = "Project-parent_project"


def remove_project_hierarchy_fields() -> None:
	"""Remove the legacy parent_project custom field from Project."""
	if frappe.db.exists("Custom Field", PARENT_PROJECT_FIELD):
		frappe.delete_doc("Custom Field", PARENT_PROJECT_FIELD, force=True)

	frappe.clear_cache(doctype="Project")
