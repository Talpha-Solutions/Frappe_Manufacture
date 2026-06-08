# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SITE_PROJECT_TYPE = "Site"
KITCHEN_PROJECT_TYPE = "Kitchen"

# Hide Unit tab when project_type is Site.
UNIT_TAB_DEPENDS_ON = f"eval:doc.project_type != '{SITE_PROJECT_TYPE}'"

# Kitchen is the primary unit — no Parent Unit. Robe, Utility, etc. link to a Kitchen unit.
PARENT_UNIT_DEPENDS_ON = (
	f"eval:doc.project_type && doc.project_type != '{SITE_PROJECT_TYPE}' "
	f"&& doc.project_type != '{KITCHEN_PROJECT_TYPE}'"
)

# Main form: Developer on Details; Unit tab after Costing + Monitor sections.
DEVELOPER_INSERT_AFTER = "department"
UNIT_TAB_INSERT_AFTER = "message"

REMOVED_PROJECT_UNIT_FIELDNAMES = (
	"fk_is_root_project",
	"fk_unit_category",
	"fk_sequence_number",
	"fk_process_template",
	"fk_unit_planning_section",
	"fk_planned_delivery_date",
	"fk_current_stage",
	"fk_overall_status",
	"fk_qr_identifier",
	"fk_completion_percentage",
	"fk_work_order",
	"fk_is_override",
	"fk_override_reason",
)

UNIT_CATEGORY_TO_PROJECT_TYPE = {
	"Kitchen": "Kitchen",
	"Robe": "Robe",
	"Utility": "Utility",
	"Vanity": "Vanity Unit",
	"Unit": "Unit",
	"Pantry": "Pantry",
}


def get_project_unit_custom_fields() -> dict:
	"""Custom fields on ERPNext Project — Unit tab hidden when project_type is Site."""
	return {
		"Project": [
			{
				"fieldname": "fk_developer",
				"fieldtype": "Link",
				"label": "Developer",
				"options": "Customer",
				"insert_after": DEVELOPER_INSERT_AFTER,
			},
			{
				"fieldname": "fk_unit_tab",
				"fieldtype": "Tab Break",
				"label": "Unit",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": UNIT_TAB_INSERT_AFTER,
			},
			{
				"fieldname": "fk_unit_hierarchy_section",
				"fieldtype": "Section Break",
				"label": "Hierarchy",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_unit_tab",
			},
			{
				"fieldname": "fk_parent_project",
				"fieldtype": "Link",
				"label": "Parent Project",
				"options": "Project",
				"link_filters": f'[["Project","project_type","=","{SITE_PROJECT_TYPE}"]]',
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_unit_hierarchy_section",
			},
			{
				"fieldname": "fk_house_number",
				"fieldtype": "Data",
				"label": "House Number",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_parent_project",
			},
			{
				"fieldname": "fk_col_break_hierarchy",
				"fieldtype": "Column Break",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_house_number",
			},
			{
				"fieldname": "fk_bedrooms",
				"fieldtype": "Int",
				"label": "Bedrooms",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_col_break_hierarchy",
			},
			{
				"fieldname": "fk_unit_qty",
				"fieldtype": "Int",
				"label": "Unit Qty",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_bedrooms",
			},
			{
				"fieldname": "fk_parent_unit_project",
				"fieldtype": "Link",
				"label": "Parent Unit",
				"options": "Project",
				"link_filters": f'[["Project","project_type","=","{KITCHEN_PROJECT_TYPE}"]]',
				"depends_on": PARENT_UNIT_DEPENDS_ON,
				"insert_after": "fk_unit_qty",
			},
			{
				"fieldname": "fk_unit_configuration_section",
				"fieldtype": "Section Break",
				"label": "Configuration",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_parent_unit_project",
			},
			{
				"fieldname": "fk_unit_configuration",
				"fieldtype": "Link",
				"label": "Project Unit Configuration",
				"options": "Project Unit Configuration",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_unit_configuration_section",
			},
			{
				"fieldname": "fk_effective_manifest",
				"fieldtype": "Link",
				"label": "Effective Manifest",
				"options": "Manifest",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_unit_configuration",
			},
			{
				"fieldname": "fk_effective_bom",
				"fieldtype": "Link",
				"label": "Effective BOM",
				"options": "BOM",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_effective_manifest",
			},
			{
				"fieldname": "fk_col_break_configuration",
				"fieldtype": "Column Break",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_effective_bom",
			},
			{
				"fieldname": "fk_unit_notes",
				"fieldtype": "Long Text",
				"label": "Unit Notes",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_col_break_configuration",
			},
			{
				"fieldname": "fk_download_qr_tab",
				"fieldtype": "Tab Break",
				"label": "Download QR",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_unit_notes",
			},
			{
				"fieldname": "fk_download_qr_html",
				"fieldtype": "HTML",
				"label": "QR Labels",
				"depends_on": UNIT_TAB_DEPENDS_ON,
				"insert_after": "fk_download_qr_tab",
			},
		]
	}


def remove_obsolete_project_unit_fields() -> None:
	for fieldname in REMOVED_PROJECT_UNIT_FIELDNAMES:
		custom_field_name = f"Project-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, force=True)


def migrate_root_flag_to_project_type() -> None:
	"""Set project_type = Site where legacy fk_is_root_project was set."""
	if not frappe.db.has_column("Project", "fk_is_root_project"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabProject`
		SET project_type = %(site)s
		WHERE IFNULL(fk_is_root_project, 0) = 1
			AND (project_type IS NULL OR project_type = '')
		""",
		{"site": SITE_PROJECT_TYPE},
	)


def migrate_unit_category_to_project_type() -> None:
	if not frappe.db.has_column("Project", "fk_unit_category"):
		return

	rows = frappe.db.sql(
		"""
		SELECT name, fk_unit_category, project_type
		FROM `tabProject`
		WHERE IFNULL(fk_unit_category, '') != ''
		""",
		as_dict=True,
	)

	for row in rows:
		if row.project_type:
			continue
		project_type = UNIT_CATEGORY_TO_PROJECT_TYPE.get(row.fk_unit_category)
		if project_type and frappe.db.exists("Project Type", project_type):
			frappe.db.set_value(
				"Project", row.name, "project_type", project_type, update_modified=False
			)


def ensure_project_unit_fields() -> None:
	remove_obsolete_project_unit_fields()
	migrate_root_flag_to_project_type()
	migrate_unit_category_to_project_type()

	field_defs = get_project_unit_custom_fields()["Project"]
	fields_to_sync = _get_project_fields_to_sync(field_defs)
	if fields_to_sync:
		create_custom_fields({"Project": fields_to_sync}, update=True)

	_update_unit_field_properties()
	frappe.clear_cache(doctype="Project")


def _update_unit_field_properties() -> None:
	"""Refresh depends_on / link_filters on existing Unit custom fields."""
	site_parent_filter = f'[["Project","project_type","=","{SITE_PROJECT_TYPE}"]]'

	for fieldname in [df["fieldname"] for df in get_project_unit_custom_fields()["Project"]]:
		custom_field_name = f"Project-{fieldname}"
		if not frappe.db.exists("Custom Field", custom_field_name):
			continue

		updates = {}
		field_def = next(
			(df for df in get_project_unit_custom_fields()["Project"] if df["fieldname"] == fieldname),
			None,
		)
		if field_def and field_def.get("insert_after"):
			updates["insert_after"] = field_def["insert_after"]

		if fieldname == "fk_developer":
			pass
		elif fieldname == "fk_parent_unit_project":
			updates["depends_on"] = PARENT_UNIT_DEPENDS_ON
			updates["link_filters"] = f'[["Project","project_type","=","{KITCHEN_PROJECT_TYPE}"]]'
		elif fieldname not in ("fk_unit_tab", "fk_download_qr_tab"):
			updates["depends_on"] = UNIT_TAB_DEPENDS_ON

		if fieldname == "fk_parent_project":
			updates["link_filters"] = site_parent_filter
			updates["mandatory_depends_on"] = ""
			updates["reqd"] = 0

		frappe.db.set_value("Custom Field", custom_field_name, updates, update_modified=False)


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
