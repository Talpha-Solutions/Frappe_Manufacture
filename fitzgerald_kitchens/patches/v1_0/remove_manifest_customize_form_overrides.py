# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Clear Customize Form overrides so Manifest DocType JSON layout applies on deploy."""

import frappe


def execute():
	for name in frappe.get_all(
		"Custom Field",
		filters={"dt": "Manifest", "fieldname": ["like", "custom_column_break_%"]},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, force=True)

	for name in frappe.get_all(
		"Property Setter",
		filters={"doc_type": "Manifest", "property": "field_order"},
		pluck="name",
	):
		frappe.delete_doc("Property Setter", name, force=True)

	frappe.clear_cache(doctype="Manifest")
