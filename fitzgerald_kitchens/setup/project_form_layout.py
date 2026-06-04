# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Reset ERPNext Project desk layout after Customize Form overrides on deploy sites."""

import frappe

from fitzgerald_kitchens.setup.project_bom_fields import remove_project_bom_fields
from fitzgerald_kitchens.setup.project_hierarchy_fields import remove_project_hierarchy_fields
from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields

# Tab breaks / sections that must not stay hidden or tabs collapse into Details + Unit.
PROJECT_LAYOUT_FIELDS_TO_UNHIDE = (
	"section_break_18",
	"costing_tab",
	"monitor_progress_tab",
	"more_info_tab",
	"connections_tab",
	"customer_details",
	"users_section",
	"section_break0",
	"project_details",
)

# Customize Form properties that break tab order on Cloud when saved from Details tab.
PROJECT_LAYOUT_PROPERTIES_TO_CLEAR = ("field_order", "insert_after")


def reset_project_form_layout() -> None:
	"""Idempotent: restore Main → Unit → Costing → Progress → More Info → Connections."""
	_remove_project_customize_form_column_breaks()
	_clear_project_layout_property_setters()
	remove_project_hierarchy_fields()
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
	for property_name in PROJECT_LAYOUT_PROPERTIES_TO_CLEAR:
		for name in frappe.get_all(
			"Property Setter",
			filters={"doc_type": "Project", "property": property_name},
			pluck="name",
		):
			frappe.delete_doc("Property Setter", name, force=True)

	for fieldname in PROJECT_LAYOUT_FIELDS_TO_UNHIDE:
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
