import frappe


def execute():
	if not frappe.db.exists("DocType", "Kitchen Configuration"):
		return

	frappe.rename_doc("DocType", "Kitchen Configuration", "Tender Configuration", force=True)

	frappe.db.set_value(
		"DocType",
		"Tender Configuration",
		"default_print_format",
		"Kitchen Configuration Tender Summary",
		update_modified=False,
	)

	if frappe.db.exists("Print Format", "Kitchen Configuration Tender Summary"):
		frappe.db.set_value(
			"Print Format",
			"Kitchen Configuration Tender Summary",
			"doc_type",
			"Tender Configuration",
			update_modified=False,
		)

	frappe.db.commit()
