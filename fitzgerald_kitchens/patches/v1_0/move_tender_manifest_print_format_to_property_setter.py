import frappe


def execute():
	"""Clear the default print format stored on the Tender Manifest DocType.

	Standard DocTypes can't keep one (saving the DocType, e.g. during a rename, throws), so it now
	comes from the Property Setter fixture instead.
	"""
	if frappe.db.exists("DocType", "Tender Manifest"):
		frappe.db.set_value("DocType", "Tender Manifest", "default_print_format", None, update_modified=False)
