# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""What to order now so it arrives in time, across every Pre Production Plan, or only the plans chosen
in the filter.

Demand is each plan's manifests x its units: a unit on the plan's Units table brings its manifest and its
delivery date; a plan without a Units table counts each manifest x its Fitted Units for Tender, needed on the
report's fallback delivery date. Manufactured items (Default Material Request Type "Manufacture") are
exploded through their BOM and are needed a few days before delivery (for manufacturing); bought-in
items are needed for delivery. Each item's need is covered earliest-first by stock, open purchase orders
and open material requests; what isn't covered must be ordered by (date first needed - the Item's Lead
Time in Days). Placeholder components (item group "Placeholders", e.g. "Carcass Board - per finish")
can't be ordered: they show the date the real item has to be chosen by.
"""

import json
import math
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from fitzgerald_kitchens.manufacturing.project_manifest import get_active_bom_no

MANUFACTURE = "Manufacture"
PLACEHOLDER_GROUP = "Placeholders"

OVERDUE, ORDER_NOW, ORDER_SOON, LATER, COVERED = "Overdue", "Order Now", "Order Soon", "Later", "Covered"
CHOOSE_ITEM, NO_BOM, NO_DATE, NOT_STOCKED = "Choose Item", "No BOM", "No Date", "Not Stocked"
# statuses that need someone to act, most urgent first
STATUS_ORDER = [OVERDUE, ORDER_NOW, CHOOSE_ITEM, NO_BOM, NO_DATE, ORDER_SOON, LATER, COVERED, NOT_STOCKED]
TO_ORDER_STATUSES = (OVERDUE, ORDER_NOW, ORDER_SOON)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_plan(filters)
	statuses = filters.get("status")
	if isinstance(statuses, str):
		statuses = frappe.parse_json(statuses) if statuses.startswith("[") else [statuses]
	if statuses:
		rows = [r for r in rows if r["status"] in statuses]
	return get_columns(), rows, None, None, get_summary(rows)


def get_plan(filters) -> list[dict]:
	as_on = getdate(filters.get("as_on") or nowdate())
	demand = get_demand(filters)
	items = _item_details({d["item_code"] for d in demand})
	stock = _stock(set(items), filters.get("warehouse"), filters.get("company"))
	window_end = add_days(as_on, 7 * cint(filters.get("window_weeks") or 4))

	by_item = defaultdict(list)
	for d in demand:
		by_item[d["item_code"]].append(d)

	rows = []
	for item_code, lines in by_item.items():
		item = items.get(item_code)
		if not item:
			continue
		dated = sorted((l for l in lines if l["need_date"]), key=lambda l: l["need_date"])
		needed = sum(l["qty"] for l in lines)
		s = stock.get(item_code, {})
		available = max(flt(s.get("available")), 0)
		# open orders / requests only add supply (stale Bin figures can be negative)
		on_order, requested = max(flt(s.get("ordered")), 0), max(flt(s.get("requested")), 0)
		supply = available + on_order + requested
		lead = cint(item.lead_time_days)  # the Item's Lead Time in Days

		# cover the earliest needs first; the first date that isn't covered drives the order date
		first_short = None
		cover = supply
		for l in dated:
			cover -= l["qty"]
			if cover < -1e-9:
				first_short = l["need_date"]
				break
		undated = sum(l["qty"] for l in lines if not l["need_date"])
		to_order = max(needed - supply, 0)
		if to_order and item.must_be_whole_number:
			to_order = math.ceil(to_order - 1e-9)
		first_need = dated[0]["need_date"] if dated else None
		order_by = add_days(first_short, -lead) if first_short else None

		placeholder = item.item_group == PLACEHOLDER_GROUP
		if any(l.get("no_bom") for l in lines):
			status = NO_BOM
		elif placeholder:
			status = CHOOSE_ITEM
			order_by = add_days(first_need, -lead) if first_need else None
			to_order = 0
		elif not item.is_stock_item:
			status, to_order = NOT_STOCKED, 0
		elif not to_order:
			status = COVERED
		elif not first_short and undated:
			status = NO_DATE
		elif getdate(order_by) < as_on:
			status = OVERDUE
		elif getdate(order_by) == as_on:
			status = ORDER_NOW
		elif getdate(order_by) <= getdate(window_end):
			status = ORDER_SOON
		else:
			status = LATER

		plans = sorted({l["plan"] for l in lines})
		units = {}
		for l in lines:
			units[l["unit"]] = l["units"]
		rows.append({
			"status": status,
			"item_code": item_code,
			"item_name": item.item_name,
			"item_group": item.item_group,
			"uom": item.stock_uom,
			"needed": needed,
			"first_need": first_need,
			"lead_time_days": lead,
			"order_by": order_by,
			"available": available,
			"on_order": on_order,
			"requested": requested,
			"to_order": to_order,
			"units": sum(units.values()),
			"plans": ", ".join(plans),
		})

	rank = {s: i for i, s in enumerate(STATUS_ORDER)}
	rows.sort(key=lambda r: (rank[r["status"]], r["order_by"] or getdate("2999-12-31"), r["item_code"]))
	return rows


# ------------------------------------------------------------------ demand


def get_demand(filters) -> list[dict]:
	"""One line per item per unit: {item_code, qty (stock UOM), need_date, unit, units, plan}."""
	manufacturing_days = cint(filters.get("manufacturing_days") if filters.get("manufacturing_days") is not None else 14)
	bought_in_days = cint(filters.get("bought_in_days") or 0)
	fallback = getdate(filters.get("default_delivery_date")) if filters.get("default_delivery_date") else None

	units = []  # (unit key, units it stands for, plan, delivery date, [(item_code, qty, uom, bom)])
	for plan in _plans(filters):
		rows = frappe.get_all("Tender Unit Type", filters={"parent": plan, "parenttype": "Pre Production Plan"},
		                      fields=["number", "project_type", "unit_no", "delivery_date", "manifest"])
		if rows:
			# the plan's units: each brings its manifest and its delivery date
			for r in rows:
				if r.manifest:
					units.append((f"{plan}:{r.number}:{r.project_type}:{r.unit_no}", 1, plan, r.delivery_date or fallback,
					              _tender_manifest_lines(r.manifest)))
		else:
			# no Units table yet: each manifest x its units to tender
			for m in frappe.get_all("Pre Production Manifest", filters={"pre_production_plan": plan},
			                        fields=["name", "kitchens_to_tender"]):
				count = cint(m.kitchens_to_tender)
				if count > 0:
					lines = [(code, qty * count, uom, bom) for code, qty, uom, bom in _tender_manifest_lines(m.name)]
					units.append((f"{plan}:{m.name}", count, plan, fallback, lines))

	manufactured = set(frappe.get_all("Item", filters={"default_material_request_type": MANUFACTURE}, pluck="name"))
	explosion_cache = {}
	demand = []
	for unit, count, plan, delivery, lines in units:
		delivery = getdate(delivery) if delivery else None
		for item_code, qty, uom, bom in lines:
			qty *= _conversion(item_code, uom)
			base = {"unit": unit, "units": count, "plan": plan}
			if item_code in manufactured:
				need = add_days(delivery, -manufacturing_days) if delivery else None
				bom = get_active_bom_no(item_code, bom)
				if not bom:
					# can't be exploded: shown as the item itself, flagged
					demand.append({**base, "item_code": item_code, "qty": qty, "need_date": need, "no_bom": True})
					continue
				for component, per_unit in _explode(bom, explosion_cache):
					demand.append({**base, "item_code": component, "qty": qty * per_unit, "need_date": need})
			else:
				need = add_days(delivery, -bought_in_days) if delivery else None
				demand.append({**base, "item_code": item_code, "qty": qty, "need_date": need})
	return demand


def _plans(filters) -> list[str]:
	"""The plans chosen in the filter; with none chosen, every plan (of the filter's company, or with no
	company). Only plans the user can read."""
	value = filters.get("pre_production_plan")
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	chosen = [v for v in (value or []) if v]
	if chosen:
		for plan in chosen:
			frappe.has_permission("Pre Production Plan", "read", plan, throw=True)
		return chosen
	company = filters.get("company")
	return [p.name for p in frappe.get_list("Pre Production Plan", fields=["name", "company"], order_by="name")
	        if not company or p.company in (company, None, "")]


def _tender_manifest_lines(manifest: str) -> list[tuple]:
	"""A Pre Production Manifest's item rows: (item_code, qty, uom, BOM it was costed from)."""
	rows = json.loads(frappe.db.get_value("Pre Production Manifest", manifest, "config_rows_json") or "[]")
	return [(r["item_code"], flt(r.get("qty")), r.get("uom"), r.get("bom") or None)
	        for r in rows if r.get("item_code") and flt(r.get("qty")) > 0]


def _explode(bom: str, cache: dict) -> list[tuple]:
	"""(raw material, stock qty per one of the BOM's item), from the BOM's exploded items."""
	if bom not in cache:
		quantity = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
		cache[bom] = [(e.item_code, flt(e.stock_qty) / quantity)
		              for e in frappe.get_all("BOM Explosion Item", filters={"parent": bom, "parenttype": "BOM"},
		                                      fields=["item_code", "stock_qty"])]
	return cache[bom]


def _conversion(item_code: str, uom: str | None) -> float:
	if not uom:
		return 1
	stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	if not stock_uom or uom == stock_uom:
		return 1
	factor = frappe.db.get_value("UOM Conversion Detail", {"parent": item_code, "uom": uom}, "conversion_factor")
	return flt(factor) or 1


# ------------------------------------------------------------------ items and stock


def _item_details(item_codes: set) -> dict:
	if not item_codes:
		return {}
	items = {i.name: i for i in frappe.get_all(
		"Item", filters={"name": ["in", list(item_codes)]},
		fields=["name", "item_name", "item_group", "stock_uom", "is_stock_item", "lead_time_days", "default_material_request_type"])}
	whole = set(frappe.get_all("UOM", filters={"must_be_whole_number": 1}, pluck="name"))
	for i in items.values():
		i.must_be_whole_number = i.stock_uom in whole
	return items


def _stock(item_codes: set, warehouse: str | None, company: str | None) -> dict:
	"""Per item: available (actual - reserved), ordered (open POs), requested (open MRs)."""
	if not item_codes:
		return {}
	filters = {"item_code": ["in", list(item_codes)]}
	if warehouse:
		lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
		filters["warehouse"] = ["in", frappe.get_all("Warehouse", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")]
	elif company:
		filters["warehouse"] = ["in", frappe.get_all("Warehouse", filters={"company": company}, pluck="name")]
	reserved = [f for f in ("reserved_qty", "reserved_qty_for_production", "reserved_qty_for_sub_contract",
	                        "reserved_qty_for_production_plan", "reserved_stock") if frappe.db.has_column("Bin", f)]
	out = defaultdict(lambda: {"available": 0.0, "ordered": 0.0, "requested": 0.0})
	for b in frappe.get_all("Bin", filters=filters, fields=["item_code", "actual_qty", "ordered_qty", "indented_qty", *reserved]):
		s = out[b.item_code]
		s["available"] += flt(b.actual_qty) - sum(flt(b.get(f)) for f in reserved if f != "reserved_stock")
		s["ordered"] += flt(b.ordered_qty)
		s["requested"] += flt(b.indented_qty)
	return out


# ------------------------------------------------------------------ output


def get_columns() -> list[dict]:
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 200},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 80},
		{"fieldname": "needed", "label": _("Needed"), "fieldtype": "Float", "width": 90},
		{"fieldname": "first_need", "label": _("First Needed"), "fieldtype": "Date", "width": 105},
		{"fieldname": "lead_time_days", "label": _("Lead Days"), "fieldtype": "Int", "width": 80},
		{"fieldname": "order_by", "label": _("Order / Choose By"), "fieldtype": "Date", "width": 125},
		{"fieldname": "available", "label": _("In Stock"), "fieldtype": "Float", "width": 85},
		{"fieldname": "on_order", "label": _("On Order"), "fieldtype": "Float", "width": 85},
		{"fieldname": "requested", "label": _("Requested"), "fieldtype": "Float", "width": 90},
		{"fieldname": "to_order", "label": _("To Order"), "fieldtype": "Float", "width": 90},
		{"fieldname": "units", "label": _("Units"), "fieldtype": "Int", "width": 65},
		{"fieldname": "plans", "label": _("Pre Production Plans"), "fieldtype": "Data", "width": 170},
	]


def get_summary(rows: list[dict]) -> list[dict]:
	count = defaultdict(int)
	for r in rows:
		count[r["status"]] += 1
	cards = [(OVERDUE, "red"), (ORDER_NOW, "orange"), (ORDER_SOON, "yellow"), (CHOOSE_ITEM, "purple"), (NO_BOM, "grey"), (NO_DATE, "grey")]
	# the last two only when there are any
	return [{"label": _(s), "value": count[s], "indicator": colour, "datatype": "Int"}
	        for s, colour in cards if count[s] or s not in (NO_BOM, NO_DATE)]


@frappe.whitelist()
def create_material_request(filters: str | dict, items: str | list) -> str:
	"""A draft Purchase Material Request for the chosen rows: [{item_code, qty, schedule_date}]."""
	frappe.has_permission("Material Request", "create", throw=True)
	filters = frappe._dict(frappe.parse_json(filters) or {})
	items = frappe.parse_json(items) or []
	company = filters.get("company") or frappe.defaults.get_user_default("Company")
	warehouse = filters.get("warehouse")
	if not warehouse or frappe.db.get_value("Warehouse", warehouse, "is_group"):
		warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if not warehouse:
		frappe.throw(_("Pick a warehouse (not a group) in the filters, or set a Default Warehouse in Stock Settings."))

	today = getdate(nowdate())
	lines = []
	for row in items:
		item = frappe.db.get_value("Item", row.get("item_code"), ["name", "is_stock_item", "item_group", "stock_uom"], as_dict=True)
		if not item or not item.is_stock_item or item.item_group == PLACEHOLDER_GROUP or flt(row.get("qty")) <= 0:
			continue
		lines.append({"item_code": item.name, "qty": flt(row["qty"]), "uom": item.stock_uom, "warehouse": warehouse,
		              "schedule_date": max(getdate(row.get("schedule_date") or today), today)})
	if not lines:
		frappe.throw(_("None of the chosen rows can be ordered (placeholders and non-stock items are left out)."))

	mr = frappe.get_doc({
		"doctype": "Material Request",
		"material_request_type": "Purchase",
		"company": company,
		"transaction_date": today,
		"schedule_date": min(l["schedule_date"] for l in lines),
		"set_warehouse": warehouse,
		"items": lines,
	})
	mr.insert()
	return mr.name
