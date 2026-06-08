# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Remove Customize Form column breaks superseded by DocType JSON fields."""

import frappe

OBSOLETE_CUSTOM_COLUMN_BREAKS = (
	"custom_column_break_ljige",
	"custom_column_break_kojnj",
	"custom_column_break_kz3na",
	"custom_column_break_lqoew",
)


def execute():
	for fieldname in OBSOLETE_CUSTOM_COLUMN_BREAKS:
		custom_field_name = f"Project Unit Configuration-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, force=True)

	for name in frappe.get_all(
		"Property Setter",
		filters={
			"doc_type": "Project Unit Configuration",
			"property": "field_order",
		},
		pluck="name",
	):
		frappe.delete_doc("Property Setter", name, force=True)

	frappe.clear_cache(doctype="Project Unit Configuration")
