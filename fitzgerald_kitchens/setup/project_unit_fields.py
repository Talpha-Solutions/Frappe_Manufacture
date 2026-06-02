# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_project_unit_custom_fields() -> dict:
	"""Custom fields on ERPNext Project to support Root/Unit (non-root) projects."""
	return {
		"Project": [
			{
				"fieldname": "fk_unit_tab",
				"fieldtype": "Tab Break",
				"label": "Unit",
				"insert_after": "bom_tab",
			},
			{
				"fieldname": "fk_unit_hierarchy_section",
				"fieldtype": "Section Break",
				"label": "Hierarchy",
				"insert_after": "fk_unit_tab",
			},
			{
				"fieldname": "fk_is_root_project",
				"fieldtype": "Check",
				"label": "Is Root Project",
				"default": "0",
				"insert_after": "fk_unit_hierarchy_section",
			},
			{
				"fieldname": "fk_parent_project",
				"fieldtype": "Link",
				"label": "Parent Project",
				"options": "Project",
				"depends_on": "eval:!doc.fk_is_root_project",
				"mandatory_depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_is_root_project",
			},
			{
				"fieldname": "fk_house_number",
				"fieldtype": "Data",
				"label": "House Number",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_parent_project",
			},
			{
				"fieldname": "fk_unit_category",
				"fieldtype": "Select",
				"label": "Unit Category",
				"options": "Kitchen\nRobe\nUtility\nVanity\nUnit\nPantry",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_house_number",
			},
			{
				"fieldname": "fk_parent_unit_project",
				"fieldtype": "Link",
				"label": "Parent Unit",
				"options": "Project",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_unit_category",
			},
			{
				"fieldname": "fk_sequence_number",
				"fieldtype": "Int",
				"label": "Sequence Number",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_parent_unit_project",
			},
			{
				"fieldname": "fk_unit_configuration_section",
				"fieldtype": "Section Break",
				"label": "Configuration",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_sequence_number",
			},
			{
				"fieldname": "fk_unit_configuration",
				"fieldtype": "Link",
				"label": "Project Unit Configuration",
				"options": "Project Unit Configuration",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_unit_configuration_section",
			},
			{
				"fieldname": "fk_effective_manifest",
				"fieldtype": "Link",
				"label": "Effective Manifest",
				"options": "Manifest",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_unit_configuration",
			},
			{
				"fieldname": "fk_effective_bom",
				"fieldtype": "Link",
				"label": "Effective BOM",
				"options": "BOM",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_effective_manifest",
			},
			{
				"fieldname": "fk_process_template",
				"fieldtype": "Link",
				"label": "Process Template",
				"options": "Unit Process Template",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_effective_bom",
			},
			{
				"fieldname": "fk_unit_planning_section",
				"fieldtype": "Section Break",
				"label": "Planning & Progress",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_process_template",
			},
			{
				"fieldname": "fk_planned_delivery_date",
				"fieldtype": "Date",
				"label": "Planned Delivery Date",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_unit_planning_section",
			},
			{
				"fieldname": "fk_current_stage",
				"fieldtype": "Select",
				"label": "Current Stage",
				"options": "Survey\nDrawing\nExport\nManufacture\nAssembly\nDespatch\nDelivery\nFitting\nHandover",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_planned_delivery_date",
			},
			{
				"fieldname": "fk_overall_status",
				"fieldtype": "Select",
				"label": "Overall Status",
				"options": "Draft\nActive\nBlocked\nCompleted\nCancelled",
				"default": "Draft",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_current_stage",
			},
			{
				"fieldname": "fk_qr_identifier",
				"fieldtype": "Data",
				"label": "QR Identifier",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_overall_status",
			},
			{
				"fieldname": "fk_is_override",
				"fieldtype": "Check",
				"label": "Is Override",
				"default": "0",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_qr_identifier",
			},
			{
				"fieldname": "fk_override_reason",
				"fieldtype": "Small Text",
				"label": "Override Reason",
				"depends_on": "eval:doc.fk_is_override",
				"insert_after": "fk_is_override",
			},
			{
				"fieldname": "fk_completion_percentage",
				"fieldtype": "Percent",
				"label": "Completion %",
				"read_only": 1,
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_override_reason",
			},
			{
				"fieldname": "fk_unit_notes",
				"fieldtype": "Long Text",
				"label": "Unit Notes",
				"depends_on": "eval:!doc.fk_is_root_project",
				"insert_after": "fk_completion_percentage",
			},
		]
	}


def ensure_project_unit_fields() -> None:
	field_defs = get_project_unit_custom_fields()["Project"]
	fields_to_sync = _get_project_fields_to_sync(field_defs)
	if fields_to_sync:
		create_custom_fields({"Project": fields_to_sync}, update=True)
	frappe.clear_cache(doctype="Project")


def _get_project_fields_to_sync(field_defs: list[dict]) -> list[dict]:
	project_fieldnames = {df.fieldname for df in frappe.get_meta("Project").get("fields")}
	fields_to_sync: list[dict] = []

	for df in field_defs:
		fieldname = df.get("fieldname")
		if not fieldname:
			continue

		if fieldname in project_fieldnames and not frappe.db.exists(
			"Custom Field", {"dt": "Project", "fieldname": fieldname}
		):
			continue

		fields_to_sync.append(df)

	return fields_to_sync

