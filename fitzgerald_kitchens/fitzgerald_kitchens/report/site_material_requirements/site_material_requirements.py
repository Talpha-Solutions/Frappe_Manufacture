# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""What a site's unit projects need in materials, set against stock (BRD 8.2 indicative stock check).

The needs come from manufacturing.site_demand (cabinets exploded through their BOMs, plus bought-in
items). Per item: available = in stock - reserved; shortfall = needed - (available + on order)
(BR-PPP-10). Read only: nothing is reserved or ordered.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from erpnext.manufacturing.doctype.bom.bom import get_valuation_rate
from fitzgerald_kitchens.manufacturing.site_demand import (
	demand_lines,
	item_details,
	stock_by_item,
	stock_warehouses,
	unit_projects,
)

# most urgent first
STATUS_ORDER = ["Order Now", "Short", "Covered by Orders", "In Stock", "Not a Stock Item"]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("site_project"):
		return get_columns(), []

	company = frappe.db.get_value("Project", filters.site_project, "company")
	needs = _totals(demand_lines(unit_projects(filters.site_project)))
	rows = _with_stock(needs, company, filters)

	if filters.get("item_group"):
		groups = set(frappe.db.get_descendants("Item Group", filters.item_group)) | {filters.item_group}
		rows = [r for r in rows if r["item_group"] in groups]
	if filters.get("only_shortfalls"):
		rows = [r for r in rows if flt(r["shortfall"]) > 0]

	rows.sort(key=lambda r: (STATUS_ORDER.index(r["status"]), r["item_group"] or "", r["item_code"]))
	return get_columns(), rows


def _totals(lines: list[dict]) -> dict:
	"""Item code -> total qty, the units needing it, the earliest date and where it comes from."""
	needs = {}
	for line in lines:
		need = needs.setdefault(line["item_code"], {"qty": 0.0, "projects": set(), "needed_by": None, "sources": set()})
		need["qty"] += line["qty"]
		need["projects"].add(line["project"])
		need["sources"].add(line["source"])
		if line["needed_by"] and (not need["needed_by"] or line["needed_by"] < need["needed_by"]):
			need["needed_by"] = line["needed_by"]
	return needs


def _with_stock(needs: dict, company: str, filters) -> list[dict]:
	if not needs:
		return []
	codes = list(needs)
	items = item_details(codes)
	stock = stock_by_item(codes, stock_warehouses(company, filters.get("warehouse")))
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
