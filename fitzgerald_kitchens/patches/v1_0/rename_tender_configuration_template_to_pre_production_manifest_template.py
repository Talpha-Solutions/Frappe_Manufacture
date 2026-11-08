import frappe

RENAMES = (
	# the child first, so the parent's rows table already points at an existing DocType
	("Tender Configuration Template Row", "Pre Production Manifest Template Row"),
	("Tender Configuration Template", "Pre Production Manifest Template"),
)


def execute():
	"""Rename Tender Configuration Template (and its Row child) to Pre Production Manifest Template.

	Runs before the model sync so the renamed JSON files sync onto the existing records:
	rename_doc renames the tables and updates every Link / Table field pointing at them
	(Pre Production Plan.template, Pre Production Manifest.template, the template's based_on).
	"""
	for old, new in RENAMES:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)
