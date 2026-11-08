import frappe

REPORT = "Site Project Overview"


def execute():
	"""The Site Project Overview report was removed from the app (its folder deleted).

	Frappe doesn't delete a standard report's record when its files go, so a site that had it would
	keep the Report in its list and an error when it's opened. Delete the record and any workspace
	links to it; its Custom Role goes with it. Deleting a standard report is allowed in a patch.
	"""
	if not frappe.db.exists("Report", REPORT):
		return

	for link_doctype in ("Workspace Link", "Workspace Shortcut"):
		frappe.db.delete(link_doctype, {"link_to": REPORT})
	frappe.delete_doc("Report", REPORT, ignore_permissions=True, ignore_missing=True)
