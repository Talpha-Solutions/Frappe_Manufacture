import frappe

from fitzgerald_kitchens.setup.development_stages import normalize_evidence_required


def execute():
	"""Convert legacy Check values (0/1) to Select (No/Yes) and set Room Surveyed to Optional."""
	for doctype in ("Development Stage", "Development Stage Line", "Development Unit Stage"):
		if not frappe.db.table_exists(f"tab{doctype}"):
			continue

		for name, value in frappe.get_all(doctype, fields=["name", "evidence_required"], as_list=True):
			new_value = normalize_evidence_required(value)
			if new_value != value:
				frappe.db.set_value(
					doctype, name, "evidence_required", new_value, update_modified=False
				)

	for doctype, filters in (
		("Development Stage", {"name": "Room Surveyed"}),
		(
			"Development Stage Line",
			{"parent": "Development Stage Settings", "stage_name": "Room Surveyed"},
		),
		("Development Unit Stage", {"stage": "Room Surveyed"}),
	):
		if not frappe.db.table_exists(f"tab{doctype}"):
			continue

		row_name = frappe.db.get_value(doctype, filters, "name")
		if row_name:
			frappe.db.set_value(
				doctype, row_name, "evidence_required", "Optional", update_modified=False
			)

	frappe.db.commit()
