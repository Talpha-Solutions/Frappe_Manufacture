# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""What a site's unit projects need in materials, set against stock (BRD 8.2 indicative stock check).

Each unit project's production Manifest lists its cabinets, with the BOM to build each from, and
its bought-in items. Cabinets are exploded through their BOM into raw materials, needed by the
unit's Manufacturing task; bought-in items are needed as they are, by its Delivery task. The
tender manifest's spec-only rows (board, door ... kept for reference) are left out.

Per item: available = in stock - reserved; shortfall = needed - (available + on order) (BR-PPP-10).
Read only: nothing is reserved or ordered.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from erpnext.manufacturing.doctype.bom.bom import get_valuation_rate
from fitzgerald_kitchens.manufacturing.project_manifest import (
	get_active_bom_no,
	is_manufacturing_item,
	resolve_project_effective_manifest,
)

MAKE_TASK_TYPE = "Manufacturing"
DELIVERY_TASK_TYPE = "Delivery"

# most urgent first
STATUS_ORDER = ["Order Now", "Short", "Covered by Orders", "In Stock", "Not a Stock Item"]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("site_project"):
		return get_columns(), []

	company = frappe.db.get_value("Project", filters.site_project, "company")
	needs = _needs(_unit_projects(filters.site_project))
	rows = _with_stock(needs, company, filters)

	if filters.get("item_group"):
		groups = set(frappe.db.get_descendants("Item Group", filters.item_group)) | {filters.item_group}
		rows = [r for r in rows if r["item_group"] in groups]
	if filters.get("only_shortfalls"):
		rows = [r for r in rows if flt(r["shortfall"]) > 0]

	rows.sort(key=lambda r: (STATUS_ORDER.index(r["status"]), r["item_group"] or "", r["item_code"]))
	return get_columns(), rows


def _unit_projects(site_project: str) -> list[str]:
	return frappe.get_all(
		"Project", filters={"fk_parent_project": site_project, "status": ["!=", "Cancelled"]}, pluck="name"
	)


def _needs(projects: list[str]) -> dict:
	"""Item code -> needed qty, the units needing it, the earliest date and where it comes from."""
	needs = {}
	exploded_cache, spec_only_cache = {}, {}
	for project in projects:
		manifest = resolve_project_effective_manifest(project)
		if not manifest:
			continue
		dates = _task_dates(project)
		spec_only = _spec_only_items(project, spec_only_cache)
		lines = frappe.get_all(
			"Manifest Item", filters={"parent": manifest}, fields=["item_code", "qty", "linked_bom"], order_by="idx"
		)
		for line in lines:
			qty = flt(line.qty)
			if not line.item_code or qty <= 0:
				continue
			if is_manufacturing_item(line.item_code, line.linked_bom):
				bom = get_active_bom_no(line.item_code, line.linked_bom)
				if bom not in exploded_cache:
					exploded_cache[bom] = _exploded(bom)
				for item_code, per_unit in exploded_cache[bom].items():
					_add(needs, item_code, per_unit * qty, project, dates[MAKE_TASK_TYPE], _("BOM"))
			elif line.item_code not in spec_only:
				_add(needs, line.item_code, qty, project, dates[DELIVERY_TASK_TYPE], _("Bought-in"))
	return needs


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
		first = first[0] if first else None
		if first:
			dates[task_type] = first
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


def _add(needs: dict, item_code: str, qty: float, project: str, needed_by, source: str):
	need = needs.setdefault(item_code, {"qty": 0.0, "projects": set(), "needed_by": None, "sources": set()})
	need["qty"] += qty
	need["projects"].add(project)
	need["sources"].add(source)
	if needed_by and (not need["needed_by"] or needed_by < need["needed_by"]):
		need["needed_by"] = needed_by


def _with_stock(needs: dict, company: str, filters) -> list[dict]:
	if not needs:
		return []
	codes = list(needs)
	items = {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters={"name": ["in", codes]},
			fields=["name", "item_name", "item_group", "stock_uom", "is_stock_item", "lead_time_days"],
		)
	}
	stock = _stock(codes, _warehouses(company, filters.get("warehouse")))
	now = getdate(today())

	rows = []
	for code, need in needs.items():
		item = items.get(code) or frappe._dict(item_name=code)
		s = stock.get(code, {})
		in_stock, reserved, on_order = flt(s.get("actual")), flt(s.get("reserved")), flt(s.get("ordered"))
		available = in_stock - reserved
		shortfall = max(0.0, need["qty"] - (available + on_order)) if item.is_stock_item else 0.0
		lead_time = int(flt(item.lead_time_days))
		order_by = add_days(need["needed_by"], -lead_time) if need["needed_by"] else None

		if not item.is_stock_item:
			status = "Not a Stock Item"
		elif shortfall > 0 and order_by and getdate(order_by) <= now:
			status = "Order Now"
		elif shortfall > 0:
			status = "Short"
		elif need["qty"] > available:
			status = "Covered by Orders"
		else:
			status = "In Stock"

		rate = get_valuation_rate({"item_code": code, "company": company}) if shortfall else 0
		rows.append(
			{
				"item_code": code,
				"item_name": item.item_name,
				"item_group": item.item_group,
				"stock_uom": item.stock_uom,
				"source": ", ".join(sorted(need["sources"])),
				"needed_qty": need["qty"],
				"units": len(need["projects"]),
				"needed_by": need["needed_by"],
				"lead_time_days": lead_time,
				"order_by": order_by,
				"in_stock": in_stock,
				"reserved": reserved,
				"available": available,
				"on_order": on_order,
				"requested": flt(s.get("requested")),
				"shortfall": shortfall,
				"shortfall_value": shortfall * flt(rate),
				"status": status,
			}
		)
	return rows


def _warehouses(company: str, warehouse: str | None) -> list[str]:
	"""The stock warehouses to count: the chosen one (and those under it), else all the company's."""
	if warehouse:
		names = set(frappe.db.get_descendants("Warehouse", warehouse)) | {warehouse}
		filters = {"name": ["in", list(names)], "is_group": 0}
	else:
		filters = {"company": company, "is_group": 0}
	return frappe.get_all("Warehouse", filters=filters, pluck="name")


def _stock(codes: list[str], warehouses: list[str]) -> dict:
	if not warehouses:
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


def get_columns() -> list[dict]:
	return [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 230},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("From"), "fieldname": "source", "fieldtype": "Data", "width": 90},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Needed"), "fieldname": "needed_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Units"), "fieldname": "units", "fieldtype": "Int", "width": 65},
		{"label": _("Needed By"), "fieldname": "needed_by", "fieldtype": "Date", "width": 100},
		{"label": _("Lead Time (Days)"), "fieldname": "lead_time_days", "fieldtype": "Int", "width": 80},
		{"label": _("Order By"), "fieldname": "order_by", "fieldtype": "Date", "width": 100},
		{"label": _("In Stock"), "fieldname": "in_stock", "fieldtype": "Float", "width": 90},
		{"label": _("Reserved"), "fieldname": "reserved", "fieldtype": "Float", "width": 85},
		{"label": _("Available"), "fieldname": "available", "fieldtype": "Float", "width": 90},
		{"label": _("On Order"), "fieldname": "on_order", "fieldtype": "Float", "width": 85},
		{"label": _("Requested"), "fieldname": "requested", "fieldtype": "Float", "width": 90},
		{"label": _("Shortfall"), "fieldname": "shortfall", "fieldtype": "Float", "width": 90},
		{"label": _("Shortfall Value"), "fieldname": "shortfall_value", "fieldtype": "Currency", "width": 110},
	]
