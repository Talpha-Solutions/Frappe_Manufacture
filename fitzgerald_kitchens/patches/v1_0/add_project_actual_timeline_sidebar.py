import frappe

from fitzgerald_kitchens.setup.workspace_sidebar import ensure_projects_sidebar


def execute():
	if frappe.db.exists("Report", "Project Actual Timeline"):
		frappe.db.set_value(
			"Report",
			"Project Actual Timeline",
			"module",
			"fitzgerald_kitchens",
			update_modified=False,
		)
	ensure_projects_sidebar()
