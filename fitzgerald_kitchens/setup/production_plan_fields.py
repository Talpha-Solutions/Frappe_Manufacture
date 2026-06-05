# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

PROJECT_SECTION_DEPENDS_ON = 'eval: doc.get_items_from == "Project"'
CUSTOMER_FILTER_DEPENDS_ON = "eval:['Sales Order','Project'].includes(doc.get_items_from)"
OBSOLETE_PRODUCTION_PLAN_FIELDS = ("fk_customer", "fk_project_filter_col_break")


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
	_ensure_customer_filter_for_projects()
	_remove_project_filter_property_setter()
	_remove_obsolete_production_plan_fields()
	create_custom_fields(get_production_plan_custom_fields(), update=True)
	_sync_project_section_custom_fields()
	frappe.clear_cache(doctype="Production Plan")
	frappe.clear_cache(doctype="Production Plan Item")


def _sync_project_section_custom_fields() -> None:
	ordered_pp_fields = [
		("fk_projects_detail", {"depends_on": PROJECT_SECTION_DEPENDS_ON, "insert_after": "material_requests"}),
		("fk_get_projects", {"depends_on": "", "insert_after": "fk_projects_detail"}),
		("fk_projects", {"depends_on": "", "insert_after": "fk_get_projects"}),
	]

	anchor_idx = (
		frappe.db.get_value("Custom Field", "Production Plan-fk_projects_detail", "idx") or 24
	)

	for offset, (fieldname, values) in enumerate(ordered_pp_fields):
		cf_name = f"Production Plan-{fieldname}"
		if frappe.db.exists("Custom Field", cf_name):
			frappe.db.set_value(
				"Custom Field",
				cf_name,
				{**values, "idx": anchor_idx + offset},
				update_modified=False,
			)

	if frappe.db.exists("Custom Field", "Production Plan Item-fk_project"):
		frappe.db.set_value(
			"Custom Field", "Production Plan Item-fk_project", {"hidden": 1}, update_modified=False
		)


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


def _ensure_customer_filter_for_projects() -> None:
	existing = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": "Production Plan",
			"field_name": "customer",
			"property": "depends_on",
		},
		"name",
	)

	if existing:
		frappe.db.set_value("Property Setter", existing, "value", CUSTOMER_FILTER_DEPENDS_ON)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Production Plan",
				"fieldname": "customer",
				"property": "depends_on",
				"value": CUSTOMER_FILTER_DEPENDS_ON,
				"property_type": "Data",
			}
		)


def _remove_obsolete_production_plan_fields() -> None:
	for fieldname in OBSOLETE_PRODUCTION_PLAN_FIELDS:
		custom_field_name = f"Production Plan-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, force=True)


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
