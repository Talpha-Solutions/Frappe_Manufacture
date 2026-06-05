# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

PROJECT_SECTION_DEPENDS_ON = 'eval: doc.get_items_from == "Project"'


def get_production_plan_custom_fields() -> dict:
	return {
		"Production Plan": [
			{
				"fieldname": "fk_projects_detail",
				"fieldtype": "Section Break",
				"label": "Projects",
				"depends_on": PROJECT_SECTION_DEPENDS_ON,
				"collapsible": 1,
				"collapsible_depends_on": "eval: doc.__islocal",
				"insert_after": "material_requests",
			},
			{
				"fieldname": "fk_get_projects",
				"fieldtype": "Button",
				"label": "Get Projects",
				"insert_after": "fk_projects_detail",
			},
			{
				"fieldname": "fk_projects",
				"fieldtype": "Table",
				"label": "Projects",
				"options": "Production Plan Project",
				"no_copy": 1,
				"insert_after": "fk_get_projects",
			},
		],
		"Production Plan Item": [
			{
				"fieldname": "fk_project",
				"fieldtype": "Link",
				"label": "Project",
				"options": "Project",
				"read_only": 1,
				"hidden": 1,
				"insert_after": "material_request_item",
			},
		],
	}


def ensure_production_plan_fields() -> None:
	_ensure_get_items_from_options()
	_remove_project_filter_property_setter()
	create_custom_fields(get_production_plan_custom_fields(), update=True)
	_sync_project_section_custom_fields()
	frappe.clear_cache(doctype="Production Plan")
	frappe.clear_cache(doctype="Production Plan Item")


def _sync_project_section_custom_fields() -> None:
	updates_by_field = {
		"fk_projects_detail": {
			"depends_on": PROJECT_SECTION_DEPENDS_ON,
			"insert_after": "material_requests",
		},
		"fk_get_projects": {"depends_on": "", "insert_after": "fk_projects_detail"},
		"fk_projects": {"depends_on": "", "insert_after": "fk_get_projects"},
		"Production Plan Item-fk_project": {
			"hidden": 1,
		},
	}

	for fieldname, values in updates_by_field.items():
		if fieldname.startswith("Production Plan Item-"):
			custom_field_name = fieldname
		else:
			custom_field_name = f"Production Plan-{fieldname}"

		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.db.set_value("Custom Field", custom_field_name, values, update_modified=False)


def _ensure_get_items_from_options() -> None:
	options = "\nSales Order\nMaterial Request\nProject"
	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Production Plan", "field_name": "get_items_from", "property": "options"},
		"name",
	)

	if existing:
		frappe.db.set_value("Property Setter", existing, "value", options)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Production Plan",
				"fieldname": "get_items_from",
				"property": "options",
				"value": options,
				"property_type": "Text",
			}
		)


def _remove_project_filter_property_setter() -> None:
	"""Restore ERPNext default project filter visibility (Sales Order only)."""
	setter_name = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": "Production Plan",
			"field_name": "project",
			"property": "depends_on",
		},
		"name",
	)
	if setter_name:
		frappe.delete_doc("Property Setter", setter_name, force=True)
