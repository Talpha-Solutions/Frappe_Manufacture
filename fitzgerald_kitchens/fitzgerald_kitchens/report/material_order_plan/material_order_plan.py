# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""A time-phased material plan: per item, in weekly, bi-weekly or monthly columns from an As On date,
what to order, what's consumed and the stock left at the end of each period.

Needs come from manufacturing.site_demand: each unit's cabinets exploded through their BOMs (consumed
at its Manufacturing task) and its bought-in items (consumed at its Delivery task). Per item, what's
available now plus what's on order covers the earliest needs first; whatever isn't covered must be
ordered by the date it's needed less the item's lead time (before the first period: Overdue).
Projected stock assumes those orders arrive when they're needed.

One row per item; each period has three columns: Ordered, Stock and Consumed. Only periods in which
something is ordered or consumed are shown. Every stock item that's bought rather than made is
listed, with or without needs. Read only: nothing is reserved or ordered.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, formatdate, get_first_day, get_last_day, getdate, today

from erpnext.manufacturing.doctype.bom.bom import get_valuation_rate
from fitzgerald_kitchens.manufacturing.site_demand import (
	demand_lines,
	item_details,
	stock_by_item,
	stock_warehouses,
	unit_projects,
)

PERIODS = ("Weekly", "Bi-Weekly", "Monthly")
# the longest horizon, about 18 months (BRD R-PIP-02); anything after it shows as Later
MAX_PERIODS = {"Weekly": 78, "Bi-Weekly": 39, "Monthly": 18}
# the columns each period gets, in order
MEASURES = (("order", "Ordered"), ("stock", "Stock"), ("consumed", "Consumed"))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = filters.get("company") or frappe.defaults.get_user_default("Company")
	currency = frappe.get_cached_value("Company", company, "default_currency")
	period = filters.get("period") if filters.get("period") in PERIODS else "Weekly"
	show_value = filters.get("show") == "Value"

	lines = [l for l in demand_lines(unit_projects(filters.get("site_project"), company)) if l["qty"] > 0]
	as_on = getdate(filters.get("as_on") or today())
	last_needed = max((getdate(l["needed_by"]) for l in lines if l["needed_by"]), default=as_on)
	periods = get_periods(as_on, period, last_needed, cint(filters.get("periods")))

	codes = sorted(set(_orderable_items(filters)) | {l["item_code"] for l in lines})
	items = item_details(codes)
	stock = stock_by_item(codes, stock_warehouses(company, filters.get("warehouse")))
	groups = _groups(filters)
	lines_by_item = {}
	for line in lines:
		lines_by_item.setdefault(line["item_code"], []).append(line)

	plans = []
	for code in codes:
		item = items.get(code)
		# non-stock items (e.g. an unresolved BOM placeholder) are never ordered
		if not item or not item.is_stock_item or (groups and item.item_group not in groups):
			continue
		plan = _plan_item(item, lines_by_item.get(code, []), stock.get(code, {}), periods)
		if cint(filters.get("only_to_order")) and not plan["total_to_order"]:
			continue
		plan["rate"] = flt(get_valuation_rate({"item_code": code, "company": company})) if show_value else 1.0
		plans.append(plan)
	plans.sort(key=lambda p: (p["item_group"] or "", p["item_code"]))

	labels = period_labels(periods, period)
	# a column for each period in which something is ordered or consumed
	used = [i for i in range(len(labels)) if any(p["order"][i] or p["consumed"][i] for p in plans)]
	return get_columns(labels, used, show_value), _rows(plans, used, currency)


def _groups(filters) -> set | None:
	if not filters.get("item_group"):
		return None
	return set(frappe.db.get_descendants("Item Group", filters.item_group)) | {filters.item_group}


def _orderable_items(filters) -> list[str]:
	"""Every enabled stock item that's bought: items made in-house (with a default BOM) aren't ordered."""
	item_filters = {"disabled": 0, "is_stock_item": 1, "has_variants": 0, "is_purchase_item": 1, "default_bom": ["is", "not set"]}
	groups = _groups(filters)
	if groups:
		item_filters["item_group"] = ["in", list(groups)]
	return frappe.get_all("Item", filters=item_filters, pluck="name")


def get_periods(as_on, period: str, until, count: int = 0) -> list[tuple]:
	"""(start, end) of each period: weeks from As On's Monday, fortnights from that Monday, or calendar
	months from As On's month. `count` periods if given, else until the one holding `until`; at most
	MAX_PERIODS either way. Dates after the last period fall in Later."""
	limit = min(count, MAX_PERIODS[period]) if count > 0 else MAX_PERIODS[period]
	monday = getdate(add_days(as_on, -as_on.weekday()))
	days = 14 if period == "Bi-Weekly" else 7
	periods = []
	while len(periods) < limit:
		if period == "Monthly":
			start = getdate(add_months(get_first_day(as_on), len(periods)))
			end = getdate(get_last_day(start))
		else:
			start = getdate(add_days(monday, len(periods) * days))
			end = getdate(add_days(start, days - 1))
		periods.append((start, end))
		if count <= 0 and end >= until:
			break
	return periods


def period_labels(periods: list[tuple], period: str) -> list[str]:
	"""Overdue first, then e.g. "Week 47 (16-11-2026)", "Weeks 47-48 (16-11-2026)" or "November
	2026", then Later."""
	labels = [_("Overdue")]
	for start, end in periods:
		if period == "Monthly":
			labels.append(_(start.strftime("%B")) + start.strftime(" %Y"))
		elif period == "Bi-Weekly":
			labels.append(
				_("Weeks {0}-{1} ({2})").format(start.isocalendar()[1], end.isocalendar()[1], formatdate(start))
			)
		else:
			labels.append(_("Week {0} ({1})").format(start.isocalendar()[1], formatdate(start)))
	labels.append(_("Later"))
	return labels


def _column(when, periods: list[tuple]) -> int:
	"""Column index for a date: 0 = before the first period, one per period, last = after them."""
	if when < periods[0][0]:
		return 0
	for i, (start, end) in enumerate(periods, start=1):
		if start <= when <= end:
			return i
	return len(periods) + 1


def _plan_item(item, lines: list[dict], stock: dict, periods: list[tuple]) -> dict:
	"""Per column: qty to order, qty consumed and the projected stock at its end."""
	available = flt(stock.get("actual")) - flt(stock.get("reserved"))
	on_order = flt(stock.get("ordered"))
	lead_time = cint(item.lead_time_days)
	width = len(periods) + 2
	plan = {
		"item_code": item.name,
		"item_group": item.item_group,
		"stock_uom": item.stock_uom,
		"lead_time_days": lead_time,
		"available": available,
		"on_order": on_order,
		"total_needed": 0.0,
		"total_to_order": 0.0,
		"order": [0.0] * width,
		"consumed": [0.0] * width,
		"stock": [0.0] * width,
	}
	first_day = periods[0][0]
	arriving = [0.0] * width  # orders placed for a need arrive in the need's column

	# earliest needs are covered first by what's in stock and on order
	cover = max(available, 0.0) + on_order
	for line in sorted(lines, key=lambda l: l["needed_by"] or first_day):
		needed_by = getdate(line["needed_by"] or first_day)
		need = line["qty"]
		short = need - min(cover, need)
		cover -= need - short
		plan["total_needed"] += need
		plan["total_to_order"] += short

		used_in = _column(needed_by, periods)
		plan["consumed"][used_in] += need
		if short:
			plan["order"][_column(getdate(add_days(needed_by, -lead_time)), periods)] += short
			arriving[used_in] += short

	# projected stock at the end of each column: start, plus orders arriving, less what's consumed
	balance = available + on_order
	for i in range(width):
		balance += arriving[i] - plan["consumed"][i]
		plan["stock"][i] = balance
	return plan


def _rows(plans: list[dict], used: list[int], currency: str) -> list[dict]:
	"""A row per item: its totals, then each period's order, consumed and stock."""
	rows = []
	for p in plans:
		row = {
			"item_code": p["item_code"],
			"item_group": p["item_group"],
			"stock_uom": p["stock_uom"],
			"lead_time_days": p["lead_time_days"],
			"available": p["available"],
			"on_order": p["on_order"],
			"total_needed": p["total_needed"],
			"total_to_order": p["total_to_order"],
			"currency": currency,
		}
		for i in used:
			for key, _label in MEASURES:
				row[f"p{i}_{key}"] = p[key][i] * p["rate"]
		rows.append(row)
	return rows


def get_columns(labels: list[str], used: list[int], show_value: bool) -> list[dict]:
	columns = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 240},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 110},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"label": _("Lead Time (Days)"), "fieldname": "lead_time_days", "fieldtype": "Int", "width": 80},
		{"label": _("Available"), "fieldname": "available", "fieldtype": "Float", "width": 90},
		{"label": _("On Order"), "fieldname": "on_order", "fieldtype": "Float", "width": 85},
		{"label": _("Total Needed"), "fieldname": "total_needed", "fieldtype": "Float", "width": 100},
		{"label": _("Total to Order"), "fieldname": "total_to_order", "fieldtype": "Float", "width": 105},
	]
	for i in used:
		for key, label in MEASURES:
			column = {"label": f"{labels[i]} · {_(label)}", "fieldname": f"p{i}_{key}", "width": 130}
			if show_value:
				column.update(fieldtype="Currency", options="currency")
			else:
				column["fieldtype"] = "Float"
			columns.append(column)
	return columns
