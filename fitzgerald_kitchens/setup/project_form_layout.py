# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Reset ERPNext Project desk layout after Customize Form overrides on deploy sites."""

import frappe

from fitzgerald_kitchens.setup.project_bom_fields import remove_project_bom_fields
from fitzgerald_kitchens.setup.project_hierarchy_fields import remove_project_hierarchy_fields
from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields


def reset_project_form_layout() -> None:
	"""Idempotent: restore Details → Unit → Costing → Progress → More Info → Connections."""
	removed_ps = _remove_all_project_property_setters()
	_remove_project_customize_form_column_breaks()
	remove_project_hierarchy_fields()
	remove_project_bom_fields()
	ensure_project_unit_fields()
	frappe.clear_cache(doctype="Project")
	frappe.reload_doc("Projects", "doctype", "Project")
	frappe.logger("fitzgerald_kitchens").info(
		f"Project form layout reset: removed {removed_ps} Property Setter(s)"
	)


def _remove_all_project_property_setters() -> int:
	"""Remove every Customize Form override on Project (field_order, hidden tabs, etc.)."""
	names = frappe.get_all("Property Setter", filters={"doc_type": "Project"}, pluck="name")
	for name in names:
		frappe.delete_doc("Property Setter", name, force=True)
	return len(names)


def _remove_project_customize_form_column_breaks() -> None:
	for name in frappe.get_all(
		"Custom Field",
		filters={"dt": "Project", "fieldname": ["like", "custom_column_break_%"]},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, force=True)
