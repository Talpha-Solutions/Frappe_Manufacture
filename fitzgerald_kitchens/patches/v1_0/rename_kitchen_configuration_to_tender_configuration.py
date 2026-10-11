import frappe


def execute():
	if not frappe.db.exists("DocType", "Kitchen Configuration"):
		return

	frappe.rename_doc("DocType", "Kitchen Configuration", "Tender Configuration", force=True)

	if frappe.db.exists("Print Format", "Kitchen Configuration Tender Summary"):
		frappe.db.set_value(
			"Print Format",
			"Kitchen Configuration Tender Summary",
			"doc_type",
			"Tender Configuration",
			update_modified=False,
		)

	frappe.db.commit()
