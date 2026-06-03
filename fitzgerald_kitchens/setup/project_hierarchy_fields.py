# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

PARENT_PROJECT_FIELD = "Project-parent_project"


def get_project_hierarchy_custom_fields() -> dict:
	"""Custom field for Site / unit project hierarchy."""
	return {
		"Project": [
			{
				"fieldname": "parent_project",
				"fieldtype": "Link",
				"label": "Parent",
				"options": "Project",
				"insert_after": "project_type",
				"in_standard_filter": 1,
			},
		]
	}


def ensure_project_hierarchy_fields() -> None:
	create_custom_fields(get_project_hierarchy_custom_fields(), update=True)


def remove_project_hierarchy_fields() -> None:
	"""Remove the parent_project custom field from Project."""
	if frappe.db.exists("Custom Field", PARENT_PROJECT_FIELD):
		frappe.delete_doc("Custom Field", PARENT_PROJECT_FIELD, force=True)

	frappe.clear_cache(doctype="Project")


def get_projects_in_scope(project: str | None) -> list[str]:
	"""Return the selected project and any linked child projects."""
	if not project:
		return []

	projects = [project]
	if not frappe.get_meta("Project").has_field("parent_project"):
		return projects

	children = frappe.get_all(
		"Project",
		filters={"parent_project": project, "docstatus": ("<", 2)},
		pluck="name",
		order_by="name",
	)
	projects.extend(children)
	return projects
