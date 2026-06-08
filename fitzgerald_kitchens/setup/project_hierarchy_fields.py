# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Site → unit hierarchy uses fk_parent_project on Project (Unit tab)."""

import frappe

PARENT_PROJECT_FIELD = "Project-parent_project"
SITE_PARENT_FIELD = "fk_parent_project"


def remove_project_hierarchy_fields() -> None:
	"""Remove legacy parent_project custom field (superseded by fk_parent_project)."""
	if frappe.db.exists("Custom Field", PARENT_PROJECT_FIELD):
		frappe.delete_doc("Custom Field", PARENT_PROJECT_FIELD, force=True)

	frappe.clear_cache(doctype="Project")


def get_projects_in_scope(project: str | None) -> list[str]:
	"""Return the selected project and any unit projects linked via fk_parent_project."""
	if not project:
		return []

	projects = [project]
	if not frappe.get_meta("Project").has_field(SITE_PARENT_FIELD):
		return projects

	children = frappe.get_all(
		"Project",
		filters={SITE_PARENT_FIELD: project, "docstatus": ("<", 2)},
		pluck="name",
		order_by="name",
	)
	projects.extend(children)
	return projects
