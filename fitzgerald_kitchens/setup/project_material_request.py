# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from fitzgerald_kitchens.setup.manifest_line_labels import (
	LABEL_CATEGORY_ASSEMBLY,
	resolve_label_category,
)
from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE

DEFAULT_MATERIAL_ISSUE_WAREHOUSE = "Stores -fkd"


@frappe.whitelist()
def make_material_request_from_project(project: str):
	"""Create a draft Material Request with items from the project's effective manifest."""
	project_doc = frappe.get_doc("Project", project)
	project_doc.check_permission("read")
	frappe.has_permission("Material Request", ptype="create", throw=True)

	if project_doc.project_type == SITE_PROJECT_TYPE:
		frappe.throw(_("Material Request can only be created from unit projects, not Site projects."))

	manifest_name = project_doc.get("fk_effective_manifest")
	if not manifest_name:
		frappe.throw(_("Set Effective Manifest on the Unit tab first."))

	if not frappe.db.exists("Manifest", manifest_name):
		frappe.throw(_("Manifest '{0}' was not found.").format(manifest_name))

	manifest = frappe.get_doc("Manifest", manifest_name)
	from_warehouse = resolve_material_issue_warehouse(project_doc.company)
	items = _manifest_lines_for_material_request(manifest, project_doc.name, from_warehouse)
	if not items:
		frappe.throw(
			_("No non-BOM manifest items found. Material Request only includes Fitting Kit and Extra lines.")
		)

	mr = frappe.new_doc("Material Request")
	mr.company = project_doc.company
	mr.material_request_type = "Material Issue"
	mr.set_warehouse = from_warehouse
	if project_doc.get("project_name"):
		mr.title = project_doc.project_name

	for row in items:
		mr.append("items", row)

	return mr.as_dict()


def resolve_material_issue_warehouse(company: str) -> str:
	"""Resolve the default source warehouse for unit Material Issue requests."""
	if not company:
		frappe.throw(_("Company is required to resolve the Material Issue warehouse."))

	warehouse = frappe.db.get_value(
		"Warehouse",
		{"name": DEFAULT_MATERIAL_ISSUE_WAREHOUSE, "company": company, "is_group": 0, "disabled": 0},
		"name",
	)
	if warehouse:
		return warehouse

	warehouse = frappe.db.get_value(
		"Warehouse",
		{
			"company": company,
			"is_group": 0,
			"disabled": 0,
			"warehouse_name": DEFAULT_MATERIAL_ISSUE_WAREHOUSE,
		},
		"name",
	)
	if warehouse:
		return warehouse

	warehouse = frappe.db.get_value(
		"Warehouse",
		{"company": company, "is_group": 0, "disabled": 0, "warehouse_name": ("like", "Stores%")},
		"name",
	)
	if warehouse:
		return warehouse

	frappe.throw(
		_("Material Issue warehouse '{0}' was not found for company {1}.").format(
			DEFAULT_MATERIAL_ISSUE_WAREHOUSE,
			company,
		)
	)


def _manifest_lines_for_material_request(
	manifest, project_name: str, from_warehouse: str
) -> list[dict]:
	rows: list[dict] = []
	item_codes = {
		line.item_code
		for line in manifest.items
		if line.item_code and flt(line.qty) > 0
	}
	item_uoms = _item_stock_uoms(item_codes)

	for line in manifest.items:
		if not line.item_code or flt(line.qty) <= 0:
			continue

		category = (line.label_category or "").strip() or resolve_label_category(
			line.item_code, line.linked_bom
		)
		if category == LABEL_CATEGORY_ASSEMBLY:
			continue

		stock_uom = item_uoms.get(line.item_code)
		if not stock_uom:
			frappe.throw(_("Default Unit of Measure is not set for Item {0}.").format(line.item_code))

		row = {
			"item_code": line.item_code,
			"qty": flt(line.qty),
			"project": project_name,
			"warehouse": from_warehouse,
			"uom": stock_uom,
			"stock_uom": stock_uom,
			"conversion_factor": 1,
		}
		if line.get("description"):
			row["description"] = line.description

		rows.append(row)

	return rows


def _item_stock_uoms(item_codes: set[str]) -> dict[str, str]:
	if not item_codes:
		return {}

	return {
		row.name: row.stock_uom
		for row in frappe.get_all(
			"Item",
			filters={"name": ("in", list(item_codes))},
			fields=["name", "stock_uom"],
		)
		if row.stock_uom
	}
