import frappe

RENAMES = (
	("Kitchen Configuration Template Row", "Tender Configuration Template Row"),
	("Kitchen Configuration Template", "Tender Configuration Template"),
)


def execute():
	"""Rename the template doctypes (tables, records and links) to Tender Configuration Template.

	Runs before model sync so the renamed doctype JSON syncs onto the existing tables. Sites already
	renamed in Desk are skipped. As a patch, rename_doc only touches the database; the app's files
	are already renamed.
	"""
	if not any(frappe.db.exists("DocType", old) for old, _new in RENAMES):
		return

	# migrate runs with developer mode on, so the rename re-saves Tender Manifest (it links to the
	# template); clear what a standard DocType can't save first (see the print format patch)
	if frappe.db.exists("DocType", "Tender Manifest"):
		frappe.db.set_value(
			"DocType",
			"Tender Manifest",
			{"default_print_format": None, "naming_rule": 'By "Naming Series" field'},
			update_modified=False,
		)

	for old, new in RENAMES:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)

	frappe.db.commit()
