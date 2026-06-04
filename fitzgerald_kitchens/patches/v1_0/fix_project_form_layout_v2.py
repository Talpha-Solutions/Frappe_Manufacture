# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Reset Project form layout: clear Customize Form overrides and re-sync Unit tab placement."""

import frappe

from fitzgerald_kitchens.setup.project_bom_fields import remove_project_bom_fields
from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields

# ERPNext tabs/sections that must stay visible for correct tabbed layout.
STANDARD_LAYOUT_FIELDS_TO_UNHIDE = (
	"section_break_18",
	"costing_tab",
	"monitor_progress_tab",
	"more_info_tab",
	"connections_tab",
)


def execute():
	_remove_project_customize_form_column_breaks()
	_clear_project_layout_property_setters()
	remove_project_bom_fields()
	ensure_project_unit_fields()
	frappe.clear_cache(doctype="Project")


def _remove_project_customize_form_column_breaks() -> None:
	for name in frappe.get_all(
		"Custom Field",
		filters={"dt": "Project", "fieldname": ["like", "custom_column_break_%"]},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, force=True)


def _clear_project_layout_property_setters() -> None:
	for name in frappe.get_all(
		"Property Setter",
		filters={"doc_type": "Project", "property": "field_order"},
		pluck="name",
	):
		frappe.delete_doc("Property Setter", name, force=True)

	for fieldname in STANDARD_LAYOUT_FIELDS_TO_UNHIDE:
		for name in frappe.get_all(
			"Property Setter",
			filters={
				"doc_type": "Project",
				"field_name": fieldname,
				"property": "hidden",
			},
			pluck="name",
		):
			frappe.delete_doc("Property Setter", name, force=True)
