import frappe

from fitzgerald_kitchens.fitzgerald_kitchens.utils.stage_tracking import normalize_stage_status


def execute():
	if not frappe.db.table_exists("tabDevelopment Unit Stage"):
		return

	for name, status in frappe.get_all(
		"Development Unit Stage", fields=["name", "status"], as_list=True
	):
		new_status = normalize_stage_status(status)
		if new_status != status:
			frappe.db.set_value(
				"Development Unit Stage", name, "status", new_status, update_modified=False
			)

	frappe.db.commit()
