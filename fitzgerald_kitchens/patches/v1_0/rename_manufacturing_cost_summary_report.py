import frappe

OLD_REPORT_NAME = "Manufacturing Cost Summary"
NEW_REPORT_NAME = "Production Cost Summary"


def execute():
	"""Rename Manufacturing Cost Summary report to Production Cost Summary."""
	if frappe.db.exists("Report", OLD_REPORT_NAME):
		if frappe.db.exists("Report", NEW_REPORT_NAME):
			frappe.delete_doc("Report", OLD_REPORT_NAME, force=True)
		else:
			frappe.rename_doc("Report", OLD_REPORT_NAME, NEW_REPORT_NAME, force=True)
			frappe.db.set_value(
				"Report",
				NEW_REPORT_NAME,
				"report_name",
				NEW_REPORT_NAME,
				update_modified=False,
			)

	_update_sidebar_links()
	frappe.db.commit()


def _update_sidebar_links():
	if not frappe.db.table_exists("tabWorkspace Sidebar Item"):
		return

	for sidebar_name in ("Projects", "Manufacturing"):
		if not frappe.db.exists("Workspace Sidebar", sidebar_name):
			continue

		sidebar = frappe.get_doc("Workspace Sidebar", sidebar_name)
		changed = False
		for row in sidebar.items:
			if row.link_to == OLD_REPORT_NAME or row.label == OLD_REPORT_NAME:
				row.link_to = NEW_REPORT_NAME
				row.label = NEW_REPORT_NAME
				changed = True

		if changed:
			sidebar.flags.ignore_permissions = True
			sidebar.save()
