# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from fitzgerald_kitchens.fitzgerald_kitchens.utils.project_manufacturing_cost import (
	get_task_metrics,
	get_work_order_metrics,
)

SITE_PROJECT_TYPE = "Site"


def _site_child_project_filters(site_names, *, project_name=None):
	"""All non-Site child projects linked to the given site projects."""
	filters = {
		"docstatus": ("<", 2),
		"project_type": ("!=", SITE_PROJECT_TYPE),
		"fk_parent_project": ("in", site_names),
	}
	if project_name:
		filters["name"] = project_name
	return filters


def execute(filters=None):
	data = get_data(filters)
	columns = get_columns(filters)
	message = _(
		"Select a Site Project with a linked Tender Configuration. Margin uses Tender Price "
		"Per Kitchen from that tender. Costs include all child projects under the site "
		"(Kitchen, Robe, Utility, and other unit types). Manufacturing and task actual costs "
		"use the From/To Date filter; expense claims, purchase, and material costs are "
		"cumulative project totals."
	)
	return columns, data, message


def get_data(filters):
	filters = frappe._dict(filters or {})
	filters.site_project = _resolve_site_project_filter(filters.get("site_project"))

	if not filters.site_project:
		return []

	return get_kitchen_unit_margin_data(filters)


def get_kitchen_unit_margin_data(filters, include_all_sites=False):
	"""Per child-project margin rows. When include_all_sites is True, all Site projects are included."""
	filters = frappe._dict(filters or {})
	if filters.get("site_project"):
		filters.site_project = _resolve_site_project_filter(filters.site_project)

	sites = _get_all_sites(filters) if include_all_sites else _get_sites_with_tender(filters)
	if not sites:
		return []

	site_by_name = {row.name: row for row in sites}
	site_names = list(site_by_name)

	unit_filters = _site_child_project_filters(site_names)
	if filters.get("kitchen_unit"):
		unit_filters["name"] = filters.kitchen_unit

	units = frappe.get_all(
		"Project",
		filters=unit_filters,
		fields=[
			"name",
			"project_name",
			"project_type",
			"fk_parent_project",
			"status",
			"total_expense_claim",
			"total_purchase_cost",
			"total_consumed_material_cost",
		],
		order_by="fk_parent_project asc, project_type asc, name asc",
	)
	if not units and not include_all_sites:
		return []

	if filters.get("tender_configuration"):
		sites = [
			row for row in sites if row.fk_tender_configuration == filters.tender_configuration
		]
		site_by_name = {row.name: row for row in sites}
		units = [row for row in units if row.fk_parent_project in site_by_name]

	if not units and not include_all_sites:
		return []

	unit_names = [row.name for row in units]
	manufacturing_costs = get_work_order_metrics(
		unit_names,
		filters.from_date,
		filters.to_date,
		status=filters.get("status") or None,
	) if unit_names else {}
	task_costs = get_task_metrics(unit_names, filters.from_date, filters.to_date) if unit_names else {}

	tender_names = {site.fk_tender_configuration for site in sites if site.fk_tender_configuration}
	tender_details = {}
	if tender_names:
		tender_details = {
			row.name: row
			for row in frappe.get_all(
				"Tender Configuration",
				filters={"name": ("in", list(tender_names))},
				fields=["name", "tender_name", "tender_price_per_kitchen"],
			)
		}
	delayed_sites = _get_delayed_site_names(list(site_by_name))

	data = []
	for unit in units:
		site = site_by_name.get(unit.fk_parent_project)
		if not site:
			continue

		tender = tender_details.get(site.fk_tender_configuration) if site.fk_tender_configuration else None
		if not include_all_sites and not tender:
			continue

		tender_price_per_kitchen = _resolve_tender_price_per_kitchen(site, tender) if tender else 0

		mfg = manufacturing_costs.get(unit.name, {})
		manufacturing_actual = flt(mfg.get("actual_cost"), 2)
		task = task_costs.get(unit.name, {})
		task_actual = flt(task.get("task_actual_cost"), 2)
		metrics = compute_profit_margin_metrics(
			manufacturing_actual,
			unit.total_expense_claim,
			unit.total_purchase_cost,
			unit.total_consumed_material_cost,
			tender_price_per_kitchen,
			task_actual_cost=task_actual,
		)

		data.append(
			{
				"site": site.name,
				"site_name": site.project_name or site.name,
				"is_site_delayed": 1 if site.name in delayed_sites else 0,
				"kitchen_unit": unit.name,
				"kitchen_name": unit.project_name or unit.name,
				"project_type": unit.project_type or "",
				"kitchen_status": unit.status or "",
				"is_kitchen_completed": 1 if unit.status == "Completed" else 0,
				"tender_configuration": tender.name if tender else "",
				"tender_name": (tender.tender_name or tender.name) if tender else "",
				**metrics,
			}
		)

	return data


def _get_delayed_site_names(site_names):
	if not site_names:
		return set()

	delayed = set()
	for row in frappe.get_all(
		"Project",
		filters={"name": ("in", site_names)},
		fields=["name", "status", "expected_end_date"],
	):
		if _is_project_delayed(row):
			delayed.add(row.name)

	return delayed


def _get_kitchen_completion_by_site(site_names):
	"""Return site names where every child project under the site has status Completed."""
	if not site_names:
		return set()

	counts = {}
	for row in frappe.get_all(
		"Project",
		filters=_site_child_project_filters(site_names),
		fields=["fk_parent_project", "status"],
	):
		site_key = row.fk_parent_project
		if site_key not in counts:
			counts[site_key] = {"total": 0, "completed": 0}
		counts[site_key]["total"] += 1
		if row.status == "Completed":
			counts[site_key]["completed"] += 1

	return {
		site
		for site, tally in counts.items()
		if tally["total"] > 0 and tally["completed"] == tally["total"]
	}


def _is_project_delayed(project):
	if project.status in ("Completed", "Cancelled"):
		return False
	if project.expected_end_date and getdate(project.expected_end_date) < getdate(today()):
		return True
	return False


def compute_profit_margin_metrics(
	manufacturing_actual,
	expense_claim,
	purchase_cost,
	consumed_material,
	tender_price_per_kitchen,
	task_actual_cost=0,
):
	"""Pure margin calculation used by the report (testable)."""
	manufacturing_actual = flt(manufacturing_actual, 2)
	task_actual_cost = flt(task_actual_cost, 2)
	expense_claim = flt(expense_claim, 2)
	purchase_cost = flt(purchase_cost, 2)
	consumed_material = flt(consumed_material, 2)
	total_cost = flt(
		manufacturing_actual + task_actual_cost + expense_claim + purchase_cost + consumed_material,
		2,
	)
	tender_price = flt(tender_price_per_kitchen, 2)
	profit_margin = flt(tender_price - total_cost, 2)
	cost_variance = flt(total_cost - tender_price, 2)
	margin_pct = flt((profit_margin / tender_price) * 100, 2) if tender_price else 0
	return {
		"manufacturing_actual_cost": manufacturing_actual,
		"task_actual_cost": task_actual_cost,
		"total_expense_claim": expense_claim,
		"total_purchase_cost": purchase_cost,
		"total_consumed_material_cost": consumed_material,
		"total_cost": total_cost,
		"tender_price_per_kitchen": tender_price,
		"profit_margin": profit_margin,
		"cost_variance": cost_variance,
		"margin_pct": margin_pct,
	}


def _resolve_site_project_filter(site_project):
	"""Accept project ID or display label from the Site Project filter."""
	if not site_project:
		return None

	site_project = str(site_project).strip()
	if " — " in site_project:
		site_project = site_project.split(" — ", 1)[0].strip()

	paren_match = re.search(r"\(([^)]+)\)\s*$", site_project)
	if paren_match:
		site_project = paren_match.group(1).strip()

	if frappe.db.exists("Project", site_project):
		return site_project

	return frappe.db.get_value(
		"Project",
		{"project_name": site_project, "project_type": "Site"},
		"name",
	)


def _resolve_tender_price_total(site=None, tender=None):
	"""Tender Price (total) from the Site Project's linked Tender Configuration."""
	if tender and flt(tender.tender_price_total):
		return flt(tender.tender_price_total)

	if site and site.fk_tender_configuration:
		price = flt(
			frappe.db.get_value(
				"Tender Configuration",
				site.fk_tender_configuration,
				"tender_price_total",
			)
		)
		if price:
			return price

	return 0


def _resolve_tender_price_per_kitchen(site, tender=None):
	"""Tender Price Per Kitchen from the Site Project's linked Tender Configuration."""
	if tender and flt(tender.tender_price_per_kitchen):
		return flt(tender.tender_price_per_kitchen)

	if site.fk_tender_configuration:
		price = flt(
			frappe.db.get_value(
				"Tender Configuration",
				site.fk_tender_configuration,
				"tender_price_per_kitchen",
			)
		)
		if price:
			return price

	price = flt(frappe.db.get_value("Project", site.name, "fk_tender_price_per_kitchen"))
	if price:
		return price

	return 0


def _get_all_sites(filters):
	site_filters = {
		"docstatus": ("<", 2),
		"company": filters.company,
		"project_type": "Site",
	}
	if filters.get("site_project"):
		site_filters["name"] = filters.site_project
	if filters.get("tender_configuration"):
		site_filters["fk_tender_configuration"] = filters.tender_configuration

	return frappe.get_all(
		"Project",
		filters=site_filters,
		fields=["name", "project_name", "fk_tender_configuration"],
		order_by="name asc",
	)


def _get_sites_with_tender(filters):
	site_filters = {
		"docstatus": ("<", 2),
		"company": filters.company,
		"project_type": "Site",
		"fk_tender_configuration": ("is", "set"),
	}
	if filters.get("site_project"):
		site_filters["name"] = filters.site_project

	return frappe.get_all(
		"Project",
		filters=site_filters,
		fields=["name", "project_name", "fk_tender_configuration"],
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def site_project_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search for Site Project filter — all Site projects with code + name label."""
	filters = frappe._dict(filters or {})

	like = f"%{txt or ''}%"
	site_filters = {
		"docstatus": ("<", 2),
		"project_type": "Site",
	}
	if filters.get("company"):
		site_filters["company"] = filters.company

	sites = frappe.get_all(
		"Project",
		filters=site_filters,
		or_filters={
			"name": ["like", like],
			"project_name": ["like", like],
		},
		fields=["name", "project_name"],
		order_by="name asc",
		limit_start=start,
		limit_page_length=page_len,
	)

	return [[row.name, _format_site_project_label(row.name, row.project_name)] for row in sites]


def _format_site_project_label(name, project_name):
	project_name = (project_name or "").strip()
	if project_name:
		return f"{project_name} ({name})"
	return name


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
			"width": 160,
		},
		{
			"label": _("Child Project"),
			"fieldname": "kitchen_unit",
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{
			"label": _("Project Name"),
			"fieldname": "kitchen_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Project Type"),
			"fieldname": "project_type",
			"fieldtype": "Data",
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
			"label": _("Tender Price Per Kitchen"),
			"fieldname": "tender_price_per_kitchen",
			"fieldtype": "Currency",
			"options": currency,
			"width": 170,
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
