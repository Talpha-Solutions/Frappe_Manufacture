import frappe


def execute():
	"""The Tender doctype became Pre Production Plan.

	Runs before model sync: renaming the DocType moves its table and records, and updates every link
	to it (Tender Manifest, the Project custom field, Tender Unit Type rows, the workflow, the print
	format). Inside a patch Frappe leaves the app's files alone; they're already under the new name.
	Sites renamed in Desk (site2) have nothing to do.
	"""
	if frappe.db.exists("DocType", "Tender") and not frappe.db.exists("DocType", "Pre Production Plan"):
		frappe.rename_doc("DocType", "Tender", "Pre Production Plan", force=True)
