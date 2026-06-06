# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.utils import flt

from erpnext.manufacturing.doctype.work_order.work_order import get_item_details


def get_projects_for_production_plan(production_plan) -> list[dict]:
	"""Return projects for the Production Plan Projects table.

	Only Company and Customer (optional) are applied here so Get Projects returns
	the full project list. Item/date/project filters belong to Sales Order flow.
	"""
	project = frappe.qb.DocType("Project")
	query = (
		frappe.qb.from_(project)
		.select(
			project.name,
			project.project_type,
			project.customer,
			project.fk_effective_manifest.as_("effective_manifest"),
			project.status,
		)
		.where(project.company == production_plan.company)
		.orderby(project.name)
	)

	if production_plan.get("customer"):
		query = query.where(project.customer == production_plan.customer)

	return query.run(as_dict=True)


def get_active_bom_no(item_code: str, linked_bom: str | None = None, project: str | None = None) -> str | None:
	if linked_bom and frappe.db.exists("BOM", {"name": linked_bom, "docstatus": 1, "is_active": 1}):
		return linked_bom

	# Direct DB lookup avoids ERPNext's get_item_details which unconditionally
	# fires a frappe.msgprint alert when no BOM is found (even with throw=False).
	bom_no = frappe.db.get_value(
		"BOM", {"item": item_code, "is_default": 1, "is_active": 1, "docstatus": 1}
	)
	if not bom_no:
		variant_of = frappe.db.get_value("Item", item_code, "variant_of")
		if variant_of:
			bom_no = frappe.db.get_value(
				"BOM", {"item": variant_of, "is_default": 1, "is_active": 1, "docstatus": 1}
			)
	return bom_no or None


def get_manifest_items_for_project(project: str, effective_manifest: str | None = None) -> list[dict]:
	manifest_name = effective_manifest or frappe.db.get_value("Project", project, "fk_effective_manifest")
	if not manifest_name:
		return []

	rows = frappe.get_all(
		"Manifest Item",
		filters={"parent": manifest_name},
		fields=["item_code", "description", "qty", "uom", "linked_bom"],
		order_by="idx asc",
	)

	items: list[dict] = []
	for row in rows:
		bom_no = get_active_bom_no(row.item_code, row.linked_bom, project=project)
		if not bom_no:
			continue

		item_details = get_item_details(row.item_code, project=project, skip_bom_info=True, throw=False)
		qty = flt(row.qty)
		if qty <= 0:
			continue

		items.append(
			{
				"project": project,
				"item_code": row.item_code,
				"description": row.description or (item_details or {}).get("description"),
				"stock_uom": (item_details or {}).get("stock_uom"),
				"bom_no": bom_no,
				"qty": qty,
			}
		)

	return items
