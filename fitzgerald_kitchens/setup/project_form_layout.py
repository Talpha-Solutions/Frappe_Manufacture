# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Project desk layout: Details (incl. Costing + Monitor) → Unit → More Info → Connections."""

import frappe
from frappe.custom.doctype.property_setter.property_setter import delete_property_setter

from fitzgerald_kitchens.setup.project_bom_fields import remove_project_bom_fields
from fitzgerald_kitchens.setup.project_hierarchy_fields import remove_project_hierarchy_fields
from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields

# ERPNext tab breaks rendered as sections on the Details tab.
COSTING_MONITOR_AS_SECTIONS = (
	("costing_tab", "Costing and Billing"),
	("monitor_progress_tab", "Monitor Progress"),
)

PRESERVED_PROPERTY_SETTERS = (("naming_series", "options"),)


def reset_project_form_layout() -> None:
	"""Idempotent layout sync for migrate / after_migrate."""
	removed = _remove_bad_project_property_setters()
	_remove_project_customize_form_column_breaks()
	_apply_costing_monitor_section_setters()
	remove_project_hierarchy_fields()
	remove_project_bom_fields()
	ensure_project_unit_fields()
	frappe.clear_cache(doctype="Project")
	frappe.reload_doc("Projects", "doctype", "Project")
	frappe.logger("fitzgerald_kitchens").info(
		f"Project form layout applied: removed {removed} override(s)"
	)


def _remove_bad_project_property_setters() -> int:
	"""Drop Customize Form overrides; keep naming series options."""
	removed = 0
	for name in frappe.get_all("Property Setter", filters={"doc_type": "Project"}, pluck="name"):
		ps = frappe.db.get_value(
			"Property Setter",
			name,
			["field_name", "property"],
			as_dict=True,
		)
		if (ps.field_name, ps.property) in PRESERVED_PROPERTY_SETTERS:
			continue
		frappe.delete_doc("Property Setter", name, force=True)
		removed += 1
	return removed


def _apply_costing_monitor_section_setters() -> None:
	for fieldname, label in COSTING_MONITOR_AS_SECTIONS:
		delete_property_setter("Project", "fieldtype", fieldname)
		delete_property_setter("Project", "label", fieldname)
		_upsert_property_setter(fieldname, "fieldtype", "Section Break", "Select")
		_upsert_property_setter(fieldname, "label", label, "Data")


def _upsert_property_setter(fieldname: str, property_name: str, value: str, property_type: str) -> None:
	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Project", "field_name": fieldname, "property": property_name},
		"name",
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": "Project",
			"fieldname": fieldname,
			"property": property_name,
			"value": value,
			"property_type": property_type,
		},
		is_system_generated=False,
	)


def _remove_project_customize_form_column_breaks() -> None:
	for name in frappe.get_all(
		"Custom Field",
		filters={"dt": "Project", "fieldname": ["like", "custom_column_break_%"]},
		pluck="name",
	):
		frappe.delete_doc("Custom Field", name, force=True)
