# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from fitzgerald_kitchens.fitzgerald_kitchens.report.project_tender_profit_margin.project_tender_profit_margin import (
	_get_all_sites,
	_get_delayed_site_names,
	_get_kitchen_completion_by_site,
	_resolve_tender_price_per_kitchen,
	_resolve_tender_price_total,
	get_kitchen_unit_margin_data,
)

SITE_SUM_FIELDS = (
	"manufacturing_actual_cost",
	"task_actual_cost",
	"total_expense_claim",
	"total_purchase_cost",
	"total_consumed_material_cost",
	"total_cost",
)


def execute(filters=None):
	data = get_data(filters)
	columns = get_columns(filters)
	message = _(
		"Site-level tender profit margin for all Site projects in the selected company, "
		"whether or not a Tender Configuration is linked. Tender Price uses the linked "
		"tender's Tender Price total. Costs are rolled up from kitchen units under each site."
	)
	return columns, data, message


def get_data(filters):
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		return []

	all_sites = _get_all_sites(filters)
	if not all_sites:
		return []

	unit_rows = get_kitchen_unit_margin_data(filters, include_all_sites=True)
	return aggregate_site_margin_rows(unit_rows, all_sites)


def _get_kitchen_counts_by_site(site_names):
	if not site_names:
		return {}

	counts = defaultdict(int)
	for row in frappe.get_all(
		"Project",
		filters={
			"docstatus": ("<", 2),
			"project_type": "Kitchen",
			"fk_parent_project": ("in", site_names),
		},
		fields=["fk_parent_project"],
	):
		counts[row.fk_parent_project] += 1

	return counts


def _get_tender_details_for_sites(sites, unit_rows=None):
	tender_names = {site.fk_tender_configuration for site in (sites or []) if site.fk_tender_configuration}
	for row in unit_rows or []:
		if row.get("tender_configuration"):
			tender_names.add(row["tender_configuration"])
	if not tender_names:
		return {}

	return {
		row.name: row
		for row in frappe.get_all(
			"Tender Configuration",
			filters={"name": ("in", list(tender_names))},
			fields=["name", "tender_name", "tender_price_total", "tender_price_per_kitchen"],
		)
	}


def _apply_site_tender_pricing(agg, tender):
	if not tender:
		agg["tender_price"] = 0
		agg["total_tender_budget"] = 0
		return

	agg["tender_price"] = flt(tender.tender_price_total, 2)
	agg["tender_price_per_kitchen"] = flt(tender.tender_price_per_kitchen, 2)
	agg["total_tender_budget"] = flt(tender.tender_price_total, 2)


def _empty_site_row(site, *, is_site_delayed, kitchen_count, tender=None, all_kitchens_completed=0):
	row = {
		"site": site.name,
		"site_name": site.project_name or site.name,
		"is_site_delayed": 1 if is_site_delayed else 0,
		"kitchen_count": kitchen_count,
		"all_kitchens_completed": 1 if all_kitchens_completed else 0,
		"tender_configuration": tender.name if tender else "",
		"tender_name": (tender.tender_name or tender.name) if tender else "",
		"tender_price": 0,
		"tender_price_per_kitchen": 0,
		"total_tender_budget": 0,
		**{field: 0 for field in SITE_SUM_FIELDS},
	}
	_apply_site_tender_pricing(row, tender)
	if not row["tender_price_per_kitchen"] and tender:
		row["tender_price_per_kitchen"] = _resolve_tender_price_per_kitchen(site, tender)
	return row


def aggregate_site_margin_rows(unit_rows, all_sites=None):
	site_names = [site.name for site in (all_sites or [])]
	delayed_sites = _get_delayed_site_names(site_names)
	kitchen_counts = _get_kitchen_counts_by_site(site_names)
	completed_sites = _get_kitchen_completion_by_site(site_names)
	tender_details = _get_tender_details_for_sites(all_sites, unit_rows)

	sites = {}
	if all_sites:
		for site in all_sites:
			tender = tender_details.get(site.fk_tender_configuration) if site.fk_tender_configuration else None
			sites[site.name] = _empty_site_row(
				site,
				is_site_delayed=site.name in delayed_sites,
				kitchen_count=kitchen_counts.get(site.name, 0),
				tender=tender,
				all_kitchens_completed=site.name in completed_sites,
			)

	for row in unit_rows or []:
		site_key = row["site"]
		if site_key not in sites:
			sites[site_key] = {
				"site": site_key,
				"site_name": row.get("site_name") or site_key,
				"is_site_delayed": row.get("is_site_delayed") or 0,
				"kitchen_count": 0,
				"all_kitchens_completed": 1 if site_key in completed_sites else 0,
				"tender_configuration": row.get("tender_configuration") or "",
				"tender_name": row.get("tender_name") or "",
				"tender_price": 0,
				"tender_price_per_kitchen": flt(row.get("tender_price_per_kitchen"), 2),
				"total_tender_budget": 0,
				**{field: 0 for field in SITE_SUM_FIELDS},
			}

		agg = sites[site_key]
		if not all_sites:
			agg["kitchen_count"] += 1
		for field in SITE_SUM_FIELDS:
			agg[field] = flt(agg[field] + flt(row.get(field)), 2)

	data = []
	for site_key in sorted(sites):
		agg = sites[site_key]
		if not agg["kitchen_count"]:
			agg["kitchen_count"] = kitchen_counts.get(site_key, 0)
		agg["all_kitchens_completed"] = 1 if site_key in completed_sites else 0

		tender = tender_details.get(agg.get("tender_configuration")) if agg.get("tender_configuration") else None
		if tender:
			_apply_site_tender_pricing(agg, tender)
		elif not agg.get("tender_price"):
			agg["tender_price"] = 0
			agg["total_tender_budget"] = 0

		total_tender = flt(agg["tender_price"], 2)
		total_cost = flt(agg["total_cost"], 2)
		profit_margin = flt(total_tender - total_cost, 2)
		cost_variance = flt(total_cost - total_tender, 2)
		margin_pct = flt((profit_margin / total_tender) * 100, 2) if total_tender else 0

		data.append(
			{
				**agg,
				"total_tender_budget": total_tender,
				"profit_margin": profit_margin,
				"cost_variance": cost_variance,
				"margin_pct": margin_pct,
			}
		)

	return data


def get_columns(filters):
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	return [
		{
			"label": _("Site"),
			"fieldname": "site",
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{
			"label": _("Site Name"),
			"fieldname": "site_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Kitchen Units"),
			"fieldname": "kitchen_count",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": _("Tender Configuration"),
			"fieldname": "tender_configuration",
			"fieldtype": "Link",
			"options": "Tender Configuration",
			"width": 150,
		},
		{
			"label": _("Tender Name"),
			"fieldname": "tender_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Tender Price"),
			"fieldname": "tender_price",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Tender Price Per Kitchen"),
			"fieldname": "tender_price_per_kitchen",
			"fieldtype": "Currency",
			"options": currency,
			"width": 170,
		},
		{
			"label": _("Total Tender Budget"),
			"fieldname": "total_tender_budget",
			"fieldtype": "Currency",
			"options": currency,
			"width": 160,
		},
		{
			"label": _("Manufacturing Actual Cost"),
			"fieldname": "manufacturing_actual_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 170,
		},
		{
			"label": _("Task Actual Cost"),
			"fieldname": "task_actual_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Total Expense Claim"),
			"fieldname": "total_expense_claim",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Total Purchase Cost"),
			"fieldname": "total_purchase_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Total Consumed Material Cost"),
			"fieldname": "total_consumed_material_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 190,
		},
		{
			"label": _("Total Cost"),
			"fieldname": "total_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 140,
		},
		{
			"label": _("Profit Margin"),
			"fieldname": "profit_margin",
			"fieldtype": "Currency",
			"options": currency,
			"width": 140,
		},
		{
			"label": _("Cost Variance"),
			"fieldname": "cost_variance",
			"fieldtype": "Currency",
			"options": currency,
			"width": 140,
		},
		{
			"label": _("Margin %"),
			"fieldname": "margin_pct",
			"fieldtype": "Percent",
			"width": 100,
		},
	]
