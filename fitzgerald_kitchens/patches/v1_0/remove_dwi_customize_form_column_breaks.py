# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Remove Customize Form column break superseded by col_break_import_template."""

import frappe

OBSOLETE_CUSTOM_COLUMN_BREAK = "custom_column_break_zdxzq"


def execute():
	custom_field_name = f"Development Workbook Import-{OBSOLETE_CUSTOM_COLUMN_BREAK}"
	if frappe.db.exists("Custom Field", custom_field_name):
		frappe.delete_doc("Custom Field", custom_field_name, force=True)

	for name in frappe.get_all(
		"Property Setter",
		filters={
			"doc_type": "Development Workbook Import",
			"property": "field_order",
		},
		pluck="name",
	):
		frappe.delete_doc("Property Setter", name, force=True)

	frappe.clear_cache(doctype="Development Workbook Import")
