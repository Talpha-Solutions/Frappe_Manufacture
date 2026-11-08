import frappe


def execute():
	"""The Tender Manifest doctype became Pre Production Manifest.

	Runs before model sync: renaming the DocType moves its table and records, and updates every link
	to it (Tender Unit Type rows, Project Unit Configuration, the Project custom fields, the print
	format, property setters). Inside a patch Frappe leaves the app's files alone; they're already
	under the new name. Sites renamed in Desk (site2) have nothing to do.
	"""
	if frappe.db.exists("DocType", "Tender Manifest") and not frappe.db.exists("DocType", "Pre Production Manifest"):
		frappe.rename_doc("DocType", "Tender Manifest", "Pre Production Manifest", force=True)
