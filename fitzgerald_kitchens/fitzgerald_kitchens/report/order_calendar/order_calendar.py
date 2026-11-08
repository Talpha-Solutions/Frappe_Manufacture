# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""What has to be ordered in each week (or month), across every Pre Production Plan or the chosen ones.

Uses the Material Order Plan's demand and stock, so the two always agree: each item's need is covered
earliest-first by stock, open purchase orders and open material requests, and every need that isn't
covered has to be ordered by (date needed - the Item's Lead Time in Days). That order date decides
the column: Overdue (before this week / month), one column per period, then Later. Placeholders and
non-stock items can't be ordered, so they're left out; see the Material Order Plan for them.
"""

import math
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, formatdate, get_first_day, getdate, nowdate

from fitzgerald_kitchens.fitzgerald_kitchens.report.material_order_plan.material_order_plan import (
	PLACEHOLDER_GROUP,
	_item_details,
	_stock,
	get_demand,
)

MAX_PERIODS = 52


def execute(filters=None):
	filters = frappe._dict(filters or {})
	periods = _periods(filters)
	rows = get_rows(filters, periods)
	return get_columns(filters, periods), rows, None, get_chart(filters, periods, rows)


def _periods(filters) -> list[tuple]:
	"""(key, label, start, end) per period, from the week / month that holds the As On date."""
	as_on = getdate(filters.get("as_on") or nowdate())
	count = min(max(cint(filters.get("periods") or 12), 1), MAX_PERIODS)
	out = []
	if filters.get("period") == "Monthly":
		start = get_first_day(as_on)
		for n in range(count):
			end = add_days(add_months(start, 1), -1)
			out.append((f"p{n}", formatdate(start, "MMM yyyy"), start, end))
			start = add_months(start, 1)
	else:
		start = add_days(as_on, -as_on.weekday())  # Monday
		for n in range(count):
			end = add_days(start, 6)
			out.append((f"p{n}", _("w/c {0}").format(formatdate(start, "dd MMM")), start, end))
			start = add_days(start, 7)
	return out


def get_rows(filters, periods) -> list[dict]:
	demand = get_demand(filters)
	items = _item_details({d["item_code"] for d in demand})
	stock = _stock(set(items), filters.get("warehouse"), filters.get("company"))
	value = filters.get("show") == "Value"
	rates = _rates(set(items)) if value else {}
	first_start, last_end = periods[0][2], periods[-1][3]

	by_item = defaultdict(list)
	for d in demand:
		by_item[d["item_code"]].append(d)

	rows = []
	for item_code, lines in by_item.items():
		item = items.get(item_code)
		if not item or not item.is_stock_item or item.item_group == PLACEHOLDER_GROUP:
			continue
		if filters.get("item_group") and item.item_group != filters.get("item_group"):
			continue
		if any(l.get("no_bom") for l in lines):
			continue  # a manufactured item without a BOM: nothing to order until it has one

		s = stock.get(item_code, {})
		supply = max(flt(s.get("available")), 0) + max(flt(s.get("ordered")), 0) + max(flt(s.get("requested")), 0)
		lead = cint(item.lead_time_days)

		# cover the earliest needs first; whatever's left of each need is ordered by its date - lead time
		buckets = defaultdict(float)
		uncovered = 0.0
		ordered = 0.0
		for l in sorted((l for l in lines if l["need_date"]), key=lambda l: l["need_date"]):
			short = l["qty"] - max(supply, 0)
			supply -= l["qty"]
			if short <= 1e-9:
				continue
			uncovered += short
			# whole units: round the running total up, so splitting a need across periods doesn't add extra
			qty = (math.ceil(uncovered - 1e-9) if item.must_be_whole_number else uncovered) - ordered
			if qty <= 1e-9:
				continue
			ordered += qty
			order_by = getdate(add_days(l["need_date"], -lead))
			if order_by < first_start:
				buckets["overdue"] += qty
			elif order_by > last_end:
				buckets["later"] += qty
			else:
				key = next(k for k, _label, start, end in periods if start <= order_by <= end)
				buckets[key] += qty
		if not ordered:
			continue

		rate, rate_source = rates.get(item_code, (0, ""))
		factor = rate if value else 1
		row = {
			"item_code": item_code,
			"item_name": item.item_name,
			"item_group": item.item_group,
			"uom": item.stock_uom,
			"lead_time_days": lead,
			"rate": rate if value else None,
			"rate_source": rate_source if value else None,
			"overdue": buckets["overdue"] * factor,
			"later": buckets["later"] * factor,
			"total": ordered * factor,
		}
		for key, *_rest in periods:
			row[key] = buckets[key] * factor
		rows.append(row)

	rows.sort(key=lambda r: (-flt(r["overdue"]), [-flt(r[k]) for k, *_x in periods], r["item_code"]))
	return rows


def _rates(item_codes: set) -> dict:
	"""{item: (rate, where it came from)}: its Standard Buying (or another buying) price, else last purchase
	rate, else valuation rate, else any other price (e.g. a selling price, so the value isn't 0)."""
	if not item_codes:
		return {}
	rates = {}
	ItemPrice = frappe.qb.DocType("Item Price")
	PriceList = frappe.qb.DocType("Price List")
	prices = (
		frappe.qb.from_(ItemPrice)
		.inner_join(PriceList)
		.on(PriceList.name == ItemPrice.price_list)
		.select(ItemPrice.item_code, ItemPrice.price_list, ItemPrice.price_list_rate, PriceList.buying)
		.where(ItemPrice.item_code.isin(list(item_codes)))
		.where(PriceList.enabled == 1)
		.run(as_dict=True)
	)
	prices.sort(key=lambda p: (p.price_list != "Standard Buying", not p.buying))
	for p in prices:
		if p.buying:
			rates.setdefault(p.item_code, (flt(p.price_list_rate), p.price_list))
	for i in frappe.get_all("Item", filters={"name": ["in", list(item_codes - set(rates))]},
	                        fields=["name", "last_purchase_rate", "valuation_rate"]):
		if flt(i.last_purchase_rate):
			rates[i.name] = (flt(i.last_purchase_rate), _("Last Purchase Rate"))
		elif flt(i.valuation_rate):
			rates[i.name] = (flt(i.valuation_rate), _("Valuation Rate"))
	for p in prices:
		rates.setdefault(p.item_code, (flt(p.price_list_rate), p.price_list))
	return rates


def get_columns(filters, periods) -> list[dict]:
	value = filters.get("show") == "Value"
	amount = {"fieldtype": "Currency"} if value else {"fieldtype": "Float"}
	columns = [
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 200},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
		{"fieldname": "lead_time_days", "label": _("Lead Days"), "fieldtype": "Int", "width": 80},
	]
	if value:
		columns.append({"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 90})
		columns.append({"fieldname": "rate_source", "label": _("Rate From"), "fieldtype": "Data", "width": 130})
	columns.append({"fieldname": "overdue", "label": _("Overdue"), "width": 95, **amount})
	columns += [{"fieldname": key, "label": label, "width": 95, **amount} for key, label, _s, _e in periods]
	columns.append({"fieldname": "later", "label": _("Later"), "width": 90, **amount})
	columns.append({"fieldname": "total", "label": _("Total"), "width": 100, **amount})
	return columns


def get_chart(filters, periods, rows) -> dict | None:
	if not rows:
		return None
	keys = ["overdue"] + [k for k, *_x in periods]
	labels = [_("Overdue")] + [label for _k, label, _s, _e in periods]
	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Order value") if filters.get("show") == "Value" else _("Order qty"),
			              "values": [round(sum(flt(r[k]) for r in rows), 2) for k in keys]}],
		},
		"type": "bar",
		"colors": ["#5e64ff"],
		"fieldtype": "Currency" if filters.get("show") == "Value" else "Float",
	}
