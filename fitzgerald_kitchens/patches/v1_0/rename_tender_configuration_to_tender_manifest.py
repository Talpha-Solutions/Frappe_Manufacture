import frappe

OLD = "Tender Configuration"
NEW = "Tender Manifest"
PRINT_FORMAT = "Kitchen Configuration Tender Summary"


def execute():
	"""Rename the Tender Configuration doctype (table, records and links) to Tender Manifest.

	Runs before model sync so the renamed doctype JSON syncs onto the existing table instead of
	creating an empty one. Sites already renamed in Desk are skipped. As a patch, rename_doc only
	touches the database; the app's files are already renamed.
	"""
	if not frappe.db.exists("DocType", OLD) or frappe.db.exists("DocType", NEW):
		return

	frappe.rename_doc("DocType", OLD, NEW, force=True)

	if frappe.db.exists("Print Format", PRINT_FORMAT):
		frappe.db.set_value("Print Format", PRINT_FORMAT, "doc_type", NEW, update_modified=False)

	frappe.db.commit()
