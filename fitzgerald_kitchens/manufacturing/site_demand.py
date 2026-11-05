# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""What unit projects need in materials, and when; and the stock to set it against.

Each unit project's production Manifest lists its cabinets, with the BOM to build each from, and
its bought-in items. Cabinets are exploded through their BOM into raw materials, needed by the
unit's Manufacturing task; bought-in items are needed as they are, by its Delivery task. The
tender manifest's spec-only rows (board, door ... kept for reference) are left out.

Used by the Site Material Requirements and Weekly Order Plan reports.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from fitzgerald_kitchens.manufacturing.project_manifest import (
	get_active_bom_no,
	is_manufacturing_item,
	resolve_project_effective_manifest,
)

MAKE_TASK_TYPE = "Manufacturing"
DELIVERY_TASK_TYPE = "Delivery"
SITE_PROJECT_TYPE = "Site"


def unit_projects(site_project: str | None = None, company: str | None = None) -> list[str]:
	"""A site's unit projects; or, with no site, every open site's in the company."""
	filters = {"status": ["not in", ["Completed", "Cancelled"]]}
	if site_project:
		filters["fk_parent_project"] = site_project
	else:
		filters["fk_parent_project"] = ["is", "set"]
		filters["project_type"] = ["!=", SITE_PROJECT_TYPE]
		if company:
			filters["company"] = company
	return frappe.get_all("Project", filters=filters, pluck="name")


def demand_lines(projects: list[str]) -> list[dict]:
	"""A line per item each unit needs: item_code, qty, needed_by, project, source."""
	lines = []
	exploded_cache, spec_only_cache = {}, {}
	for project in projects:
		manifest = resolve_project_effective_manifest(project)
		if not manifest:
			continue
		dates = _task_dates(project)
		spec_only = _spec_only_items(project, spec_only_cache)
		manifest_lines = frappe.get_all(
			"Manifest Item", filters={"parent": manifest}, fields=["item_code", "qty", "linked_bom"], order_by="idx"
		)
		for line in manifest_lines:
			qty = flt(line.qty)
			if not line.item_code or qty <= 0:
				continue
			if is_manufacturing_item(line.item_code, line.linked_bom):
				bom = get_active_bom_no(line.item_code, line.linked_bom)
				if bom not in exploded_cache:
					exploded_cache[bom] = _exploded(bom)
				for item_code, per_unit in exploded_cache[bom].items():
					lines.append(_line(item_code, per_unit * qty, dates[MAKE_TASK_TYPE], project, _("BOM")))
			elif line.item_code not in spec_only:
				lines.append(_line(line.item_code, qty, dates[DELIVERY_TASK_TYPE], project, _("Bought-in")))
	return lines


def _line(item_code, qty, needed_by, project, source) -> dict:
	return {"item_code": item_code, "qty": qty, "needed_by": needed_by, "project": project, "source": source}


def _exploded(bom: str) -> dict:
	"""Raw materials for one unit of the BOM's item, from its exploded items (all levels)."""
	bom_qty = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
	out = {}
	for row in frappe.get_all("BOM Explosion Item", filters={"parent": bom}, fields=["item_code", "stock_qty"]):
		out[row.item_code] = out.get(row.item_code, 0) + flt(row.stock_qty) / bom_qty
	return out


def _task_dates(project: str) -> dict:
	"""When the unit needs its materials: its Manufacturing task's start for what goes into its
	cabinets, its Delivery task's start for bought-in items; the project's dates if it has neither."""
	start, end = frappe.db.get_value("Project", project, ["expected_start_date", "expected_end_date"])
	dates = {MAKE_TASK_TYPE: start, DELIVERY_TASK_TYPE: end or start}
	for task_type in dates:
		first = frappe.get_all(
			"Task",
			filters={"project": project, "type": task_type, "exp_start_date": ["is", "set"]},
			order_by="exp_start_date asc",
			limit=1,
			pluck="exp_start_date",
		)
		if first:
			dates[task_type] = first[0]
	return {k: getdate(v) if v else None for k, v in dates.items()}


def _spec_only_items(project: str, cache: dict) -> set:
	"""Items on the unit's tender manifest only as a spec reference (not priced, not supplied as such)."""
	tender_manifest = frappe.db.get_value("Project", project, "fk_tender_manifest")
	if not tender_manifest:
		return set()
	if tender_manifest not in cache:
		rows = json.loads(frappe.db.get_value("Tender Manifest", tender_manifest, "config_rows_json") or "[]")
		cache[tender_manifest] = {r.get("item_code") for r in rows if r.get("exclude_from_price") and r.get("item_code")}
	return cache[tender_manifest]


def item_details(codes: list[str]) -> dict:
	return {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters={"name": ["in", codes or [""]]},
			fields=["name", "item_name", "item_group", "stock_uom", "is_stock_item", "lead_time_days"],
		)
	}


def stock_warehouses(company: str | None, warehouse: str | None = None) -> list[str]:
	"""The stock warehouses to count: the chosen one (and those under it), else all the company's."""
	if warehouse:
		names = set(frappe.db.get_descendants("Warehouse", warehouse)) | {warehouse}
		filters = {"name": ["in", list(names)], "is_group": 0}
	else:
		filters = {"is_group": 0, **({"company": company} if company else {})}
	return frappe.get_all("Warehouse", filters=filters, pluck="name")


def stock_by_item(codes: list[str], warehouses: list[str]) -> dict:
	"""Per item: actual, reserved (sales, production, subcontracting, stock reservations), ordered
	(open purchase orders) and requested (open material requests)."""
	if not codes or not warehouses:
		return {}
	bins = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", codes], "warehouse": ["in", warehouses]},
		fields=[
			"item_code",
			"actual_qty",
			"reserved_qty",
			"reserved_qty_for_production",
			"reserved_qty_for_sub_contract",
			"reserved_stock",
			"ordered_qty",
			"indented_qty",
		],
	)
	out = {}
	for b in bins:
		s = out.setdefault(b.item_code, {"actual": 0.0, "reserved": 0.0, "ordered": 0.0, "requested": 0.0})
		s["actual"] += flt(b.actual_qty)
		s["reserved"] += (
			flt(b.reserved_qty)
			+ flt(b.reserved_qty_for_production)
			+ flt(b.reserved_qty_for_sub_contract)
			+ flt(b.reserved_stock)
		)
		s["ordered"] += flt(b.ordered_qty)
		s["requested"] += flt(b.indented_qty)
	return out
