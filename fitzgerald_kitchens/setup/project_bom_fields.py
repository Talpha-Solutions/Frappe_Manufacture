# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

PROJECT_BOM_FIELDS = [
	"kitchen_required",
	"kitchen_type",
	"kitchen_specification",
	"kitchen_bom",
	"kitchen_item",
	"kitchen_work_order",
	"wardrobe_required",
	"wardrobe_type",
	"wardrobe_specification",
	"wardrobe_bom",
	"wardrobe_item",
	"wardrobe_work_order",
]


def get_project_bom_custom_fields() -> dict:
	"""Custom fields for Project: Connections tab, BOM tab (two-column kitchen/wardrobe)."""
	return {
		"Project": [
			{
				"fieldname": "connections_tab",
				"fieldtype": "Tab Break",
				"label": "Connections",
				"show_dashboard": 1,
				"insert_after": "message",
			},
			{
				"fieldname": "bom_tab",
				"fieldtype": "Tab Break",
				"label": "BOM",
				"insert_after": "connections_tab",
			},
			{
				"fieldname": "manufacturing_section",
				"fieldtype": "Section Break",
				"label": "BOM / Manufacturing Links",
				"insert_after": "bom_tab",
			},
			{
				"fieldname": "kitchen_required",
				"fieldtype": "Check",
				"label": "Kitchen Required",
				"default": "0",
				"insert_after": "manufacturing_section",
			},
			{
				"fieldname": "kitchen_type",
				"fieldtype": "Link",
				"label": "Kitchen Type",
				"options": "Kitchen Type",
				"depends_on": "eval:doc.kitchen_required",
				"mandatory_depends_on": "eval:doc.kitchen_required",
				"insert_after": "kitchen_required",
			},
			{
				"fieldname": "kitchen_specification",
				"fieldtype": "Link",
				"label": "Kitchen Specification",
				"options": "Kitchen Specification",
				"depends_on": "eval:doc.kitchen_required",
				"insert_after": "kitchen_type",
			},
			{
				"fieldname": "kitchen_work_order",
				"fieldtype": "Link",
				"label": "Kitchen Work Order",
				"options": "Work Order",
				"depends_on": "eval:doc.kitchen_required",
				"insert_after": "kitchen_specification",
			},
			{
				"fieldname": "fk_bom_column_break_kitchen",
				"fieldtype": "Column Break",
				"insert_after": "kitchen_work_order",
			},
			{
				"fieldname": "kitchen_bom",
				"fieldtype": "Link",
				"label": "Kitchen BOM",
				"options": "BOM",
				"depends_on": "eval:doc.kitchen_required",
				"insert_after": "fk_bom_column_break_kitchen",
			},
			{
				"fieldname": "kitchen_item",
				"fieldtype": "Link",
				"label": "Kitchen Item",
				"options": "Item",
				"depends_on": "eval:doc.kitchen_required",
				"insert_after": "kitchen_bom",
			},
			{
				"fieldname": "wardrobe_required",
				"fieldtype": "Check",
				"label": "Wardrobe Required",
				"default": "0",
				"insert_after": "kitchen_item",
			},
			{
				"fieldname": "wardrobe_type",
				"fieldtype": "Link",
				"label": "Wardrobe Type",
				"options": "Wardrobe Type",
				"depends_on": "eval:doc.wardrobe_required",
				"mandatory_depends_on": "eval:doc.wardrobe_required",
				"insert_after": "wardrobe_required",
			},
			{
				"fieldname": "wardrobe_specification",
				"fieldtype": "Link",
				"label": "Wardrobe Specification",
				"options": "Wardrobe Specification",
				"depends_on": "eval:doc.wardrobe_required",
				"insert_after": "wardrobe_type",
			},
			{
				"fieldname": "wardrobe_work_order",
				"fieldtype": "Link",
				"label": "Wardrobe Work Order",
				"options": "Work Order",
				"depends_on": "eval:doc.wardrobe_required",
				"insert_after": "wardrobe_specification",
			},
			{
				"fieldname": "fk_bom_column_break_wardrobe",
				"fieldtype": "Column Break",
				"insert_after": "wardrobe_work_order",
			},
			{
				"fieldname": "wardrobe_bom",
				"fieldtype": "Link",
				"label": "Wardrobe BOM",
				"options": "BOM",
				"depends_on": "eval:doc.wardrobe_required",
				"insert_after": "fk_bom_column_break_wardrobe",
			},
			{
				"fieldname": "wardrobe_item",
				"fieldtype": "Link",
				"label": "Wardrobe Item",
				"options": "Item",
				"depends_on": "eval:doc.wardrobe_required",
				"insert_after": "wardrobe_bom",
			},
		]
	}


WORK_ORDER_BUTTON_FIELDS = ("create_kitchen_work_order_btn", "create_wardrobe_work_order_btn")

OBSOLETE_BOM_FIELDS = (
	"fk_bom_section_break_wardrobe",
	"fk_bom_column_break_wardrobe_right",
)


def ensure_project_bom_fields() -> None:
	cleanup_obsolete_bom_fields()
	create_custom_fields(get_project_bom_custom_fields(), update=True)
	frappe.clear_cache(doctype="Project")


def cleanup_obsolete_bom_fields() -> None:
	"""Remove extra column/section breaks that caused a middle column in BOM layout."""
	import frappe

	for fieldname in OBSOLETE_BOM_FIELDS + WORK_ORDER_BUTTON_FIELDS:
		custom_field_name = f"Project-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, force=True)


def remove_work_order_button_fields() -> None:
	"""Remove legacy in-form Button fields; work orders use toolbar Create menu."""
	cleanup_obsolete_bom_fields()


def ensure_connections_tab() -> None:
	"""Ensure Connections tab exists and BOM tab follows it."""
	import frappe

	create_custom_fields(get_project_bom_custom_fields(), update=True)

	if frappe.db.exists("Custom Field", "Project-bom_tab"):
		frappe.db.set_value(
			"Custom Field",
			"Project-bom_tab",
			"insert_after",
			"connections_tab",
			update_modified=False,
		)

	frappe.clear_cache(doctype="Project")
