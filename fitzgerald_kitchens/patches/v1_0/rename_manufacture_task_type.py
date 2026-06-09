import frappe


def execute():
	"""Rename legacy Task Type 'Manufacture' to 'Manufacturing' and update linked tasks."""
	if not frappe.db.table_exists("tabTask Type"):
		return

	if not frappe.db.exists("Task Type", "Manufacture"):
		return

	if frappe.db.exists("Task Type", "Manufacturing"):
		frappe.db.set_value(
			"Task",
			{"type": "Manufacture"},
			"type",
			"Manufacturing",
			update_modified=False,
		)
		frappe.delete_doc("Task Type", "Manufacture", force=True)
	else:
		frappe.rename_doc("Task Type", "Manufacture", "Manufacturing", force=True)

	frappe.db.commit()
