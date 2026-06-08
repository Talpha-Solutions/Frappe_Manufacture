# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_projects_settings_custom_fields() -> dict:
	return {
		"Projects Settings": [
			{
				"fieldname": "fk_capacity_pipeline_section",
				"fieldtype": "Section Break",
				"label": "Capacity Pipeline Report",
				"insert_after": "fetch_timesheet_in_sales_invoice",
			},
			{
				"fieldname": "fk_capacity_pipeline_default_boms",
				"fieldtype": "Table",
				"label": "Default BOM by Company",
				"options": "Capacity Pipeline Default BOM",
				"description": (
					"Default BOM filter when opening the Capacity Pipeline Report "
					"for each company."
				),
				"insert_after": "fk_capacity_pipeline_section",
			},
		],
	}


def ensure_projects_settings_fields() -> None:
	create_custom_fields(get_projects_settings_custom_fields(), update=True)
	_ensure_projects_manager_settings_permission()
	frappe.clear_cache(doctype="Projects Settings")


def _ensure_projects_manager_settings_permission() -> None:
	if not frappe.db.exists("DocType", "Projects Settings"):
		return

	existing = frappe.db.exists(
		"Custom DocPerm",
		{
			"parent": "Projects Settings",
			"role": "Projects Manager",
			"permlevel": 0,
		},
	)
	if existing:
		return

	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": "Projects Settings",
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": "Projects Manager",
			"permlevel": 0,
			"read": 1,
			"write": 1,
		}
	).insert(ignore_permissions=True)


def validate_projects_settings(doc, method=None):
	seen_companies = set()
	for row in doc.get("fk_capacity_pipeline_default_boms") or []:
		if not row.company or not row.default_bom:
			continue

		if row.company in seen_companies:
			frappe.throw(
				_("Company {0} appears more than once in Capacity Pipeline defaults.").format(
					row.company
				)
			)
		seen_companies.add(row.company)

		bom = frappe.db.get_value(
			"BOM",
			row.default_bom,
			["company", "docstatus", "is_active"],
			as_dict=True,
		)
		if not bom:
			frappe.throw(_("BOM {0} does not exist.").format(row.default_bom))
		if bom.docstatus != 1 or not bom.is_active:
			frappe.throw(_("BOM {0} must be submitted and active.").format(row.default_bom))
		if bom.company != row.company:
			frappe.throw(
				_("BOM {0} belongs to {1}, not {2}.").format(
					row.default_bom, bom.company, row.company
				)
			)
