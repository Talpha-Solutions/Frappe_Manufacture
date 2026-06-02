# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Legacy Project BOM tab fields — removed in favour of Unit tab (fk_effective_bom, Manifest)."""

import frappe

PROJECT_BOM_FIELDNAMES = (
	"bom_tab",
	"manufacturing_section",
	"kitchen_required",
	"kitchen_type",
	"kitchen_specification",
	"kitchen_bom",
	"kitchen_item",
	"kitchen_work_order",
	"fk_bom_column_break_kitchen",
	"wardrobe_section",
	"wardrobe_required",
	"wardrobe_type",
	"wardrobe_specification",
	"wardrobe_bom",
	"wardrobe_item",
	"wardrobe_work_order",
	"fk_bom_column_break_wardrobe",
	"create_kitchen_work_order_btn",
	"create_wardrobe_work_order_btn",
	"fk_bom_section_break_wardrobe",
	"fk_bom_column_break_wardrobe_right",
)

# Kept for patches that imported PROJECT_BOM_FIELDS from Development Unit migration
PROJECT_BOM_FIELDS = (
	"kitchen_required",
	"kitchen_type",
	"kitchen_specification",
	"kitchen_bom",
	"kitchen_item",
	"kitchen_work_order",
	"wardrobe_section",
	"wardrobe_required",
	"wardrobe_type",
	"wardrobe_specification",
	"wardrobe_bom",
	"wardrobe_item",
	"wardrobe_work_order",
)


def remove_project_bom_fields() -> None:
	"""Delete custom fields for the legacy Project BOM / Kitchen / Wardrobe tab."""
	cleanup_duplicate_connections_tab()

	for fieldname in PROJECT_BOM_FIELDNAMES:
		custom_field_name = f"Project-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, force=True)

	frappe.clear_cache(doctype="Project")


def cleanup_duplicate_connections_tab() -> None:
	"""Remove custom `connections_tab` if created; ERPNext already ships it on Project."""
	custom_field_name = "Project-connections_tab"
	if frappe.db.exists("Custom Field", custom_field_name):
		frappe.delete_doc("Custom Field", custom_field_name, force=True)


# Backwards compatibility for old patches
def ensure_project_bom_fields() -> None:
	remove_project_bom_fields()


def ensure_connections_tab() -> None:
	cleanup_duplicate_connections_tab()
	frappe.clear_cache(doctype="Project")


def cleanup_obsolete_bom_fields() -> None:
	remove_project_bom_fields()


def remove_work_order_button_fields() -> None:
	remove_project_bom_fields()
