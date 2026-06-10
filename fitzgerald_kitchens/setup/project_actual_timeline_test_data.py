# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Demo data for Project Actual Timeline report.

Sets expected + actual start/end dates on Site projects and kitchen unit children
so the scheduled vs actual Gantt chart has predictable bars.

Run::

    bench --site kitchen.local execute fitzgerald_kitchens.setup.project_actual_timeline_test_data.seed_kitchen_local_project_actual_timeline_test_data
    bench --site kitchen.local execute fitzgerald_kitchens.setup.project_actual_timeline_test_data.verify_kitchen_local_project_actual_timeline_test_data

    bench --site travel.com execute fitzgerald_kitchens.setup.project_actual_timeline_test_data.seed_travel_com_project_actual_timeline_test_data
    bench --site travel.com execute fitzgerald_kitchens.setup.project_actual_timeline_test_data.verify_travel_com_project_actual_timeline_test_data
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, getdate, today

from fitzgerald_kitchens.setup.capacity_pipeline_test_data import (
	KITCHEN_LOCAL_EXPECTED,
	KITCHEN_LOCAL_SITE,
	_resolve_company,
)

MARKER = "Project Actual Timeline test data"

# kitchen.local — child kitchen projects under Riverside Site
PAT_KITCHEN_LOCAL_SITE_TIMELINE = {
	"expected_start_date": "2026-06-01",
	"expected_end_date": "2026-08-31",
	"actual_start_date": "2026-06-02",
	"actual_end_date": None,
	"status": "Open",
}

PAT_KITCHEN_LOCAL_UNIT_TIMELINES = {
	"Alpha Kitchens": {
		"expected_start_date": "2026-06-01",
		"expected_end_date": "2026-07-20",
		"actual_start_date": "2026-06-05",
		"actual_end_date": None,
		"status": "Open",
	},
	"Beta Kitchens": {
		"expected_start_date": "2026-06-10",
		"expected_end_date": "2026-08-01",
		"actual_start_date": "2026-06-12",
		"actual_end_date": "2026-07-28",
		"status": "Completed",
	},
	"Riverside Kitchen 02": {
		"expected_start_date": "2026-06-15",
		"expected_end_date": "2026-08-15",
		"actual_start_date": "2026-06-08",
		"actual_end_date": None,
		"status": "In Progress",
	},
	"Gamma Kitchens": {
		# Delayed completed unit — finished after expected end date.
		"expected_start_date": "2026-05-01",
		"expected_end_date": "2026-05-20",
		"actual_start_date": "2026-05-08",
		"actual_end_date": "2026-06-02",
		"status": "Completed",
	},
}

# travel.com — The Lane MOCKSITE unit rows (matches workbook-style labels)
PAT_TRAVEL_LANE_SITE = "PROJ-0015"
PAT_TRAVEL_LANE_SITE_NAME = "The Lane MOCKSITE"
PAT_TRAVEL_LANE_UNIT_TIMELINES = {
	"Unit 1 | Kitchen | The Lane MOCKSITE": {
		# Delayed: expected end passed while still in progress (chart bar extends past schedule).
		"expected_start_date": "2026-05-05",
		"expected_end_date": "2026-05-25",
		"actual_start_date": "2026-05-17",
		"actual_end_date": None,
		"status": "In Progress",
	},
	"Unit 2 | Kitchen | The Lane MOCKSITE": {
		"expected_start_date": "2026-05-08",
		"expected_end_date": "2026-06-25",
		"actual_start_date": "2026-05-15",
		"actual_end_date": None,
		"status": "Open",
	},
	"Unit 3 | Kitchen | The Lane MOCKSITE": {
		"expected_start_date": "2026-05-10",
		"expected_end_date": "2026-06-30",
		"actual_start_date": "2026-05-13",
		"actual_end_date": None,
		"status": "Open",
	},
}


def seed_kitchen_local_project_actual_timeline_test_data():
	"""Seed Riverside Site + kitchen units with scheduled and actual timeline dates."""
	company = _resolve_company()
	site_id = _ensure_kitchen_local_timeline_site(company)

	updated = []
	updated.append(_apply_timeline(site_id, PAT_KITCHEN_LOCAL_SITE_TIMELINE, label=KITCHEN_LOCAL_SITE))

	for project_name, timeline in PAT_KITCHEN_LOCAL_UNIT_TIMELINES.items():
		project_id = _ensure_kitchen_local_unit(site_id, project_name, company)
		updated.append(_apply_timeline(project_id, timeline, label=project_name))

	frappe.db.commit()
	report_rows = _get_report_rows(company, site_id)

	return {
		"marker": MARKER,
		"company": company,
		"site": KITCHEN_LOCAL_SITE,
		"site_id": site_id,
		"updated_projects": updated,
		"report_filters": _kitchen_local_report_filters(company, site_id),
		"report_row_count": len(report_rows),
		"report_rows": report_rows,
	}


def verify_kitchen_local_project_actual_timeline_test_data():
	company = _resolve_company()
	site_id = _resolve_site_by_name(KITCHEN_LOCAL_SITE)
	if not site_id:
		frappe.throw("Run seed_kitchen_local_project_actual_timeline_test_data first.")

	report_rows = _get_report_rows(company, site_id)
	report_names = {row["project_name"] for row in report_rows}
	expected_units = set(PAT_KITCHEN_LOCAL_UNIT_TIMELINES)

	checks = [
		{
			"check": "site_on_report",
			"ok": site_id in {row["site"] for row in report_rows} or bool(report_rows),
			"expected": "kitchen units under site",
			"actual": len(report_rows),
		},
		{
			"check": "all_demo_units_present",
			"ok": expected_units.issubset(report_names),
			"expected": sorted(expected_units),
			"actual": sorted(report_names),
		},
		{
			"check": "scheduled_and_actual_dates",
			"ok": all(
				row.get("expected_start_date")
				and row.get("expected_end_date")
				and row.get("actual_start_date")
				for row in report_rows
				if row["project_name"] in expected_units
			),
			"expected": "expected + actual start on each demo unit",
			"actual": [
				{
					"project": row["project_name"],
					"expected_start": row.get("expected_start_date"),
					"expected_end": row.get("expected_end_date"),
					"actual_start": row.get("actual_start_date"),
					"actual_end": row.get("actual_end_date"),
				}
				for row in report_rows
				if row["project_name"] in expected_units
			],
		},
		{
			"check": "delayed_unit_present",
			"ok": any(row.get("schedule_status") == "Late" for row in report_rows),
			"expected": "Gamma Kitchens completed after expected end",
			"actual": [
				{
					"project": row["project_name"],
					"schedule_status": row.get("schedule_status"),
					"delay_days": row.get("delay_days"),
				}
				for row in report_rows
				if row.get("schedule_status") == "Late"
			],
		},
	]

	return {
		"all_passed": all(row["ok"] for row in checks),
		"checks": checks,
		"report_filters": _kitchen_local_report_filters(company, site_id),
		"report_rows": report_rows,
	}


def seed_travel_com_project_actual_timeline_test_data():
	"""Seed The Lane MOCKSITE kitchen units with timeline dates on travel.com."""
	company = _resolve_travel_company()
	site_id = _resolve_travel_lane_site()
	if not site_id:
		frappe.throw(
			f"Site {PAT_TRAVEL_LANE_SITE!r} / {PAT_TRAVEL_LANE_SITE_NAME!r} not found on this site."
		)

	updated = []
	for project_name, timeline in PAT_TRAVEL_LANE_UNIT_TIMELINES.items():
		project_id = _ensure_lane_kitchen_unit(site_id, project_name, company)
		updated.append(_apply_timeline(project_id, timeline, label=project_name))

	frappe.db.commit()
	report_rows = _get_report_rows(company, site_id)

	return {
		"marker": MARKER,
		"company": company,
		"site_id": site_id,
		"updated_projects": updated,
		"report_filters": _travel_report_filters(company, site_id),
		"report_row_count": len(report_rows),
		"report_rows": report_rows,
	}


def verify_travel_com_all_sites_timeline_test_data():
	"""Verify report shows site rollup rows when Site Project filter is empty."""
	company = _resolve_travel_company()
	report_rows = _get_report_rows(company, site_id=None)
	lane_rows = [row for row in report_rows if row.get("project") == PAT_TRAVEL_LANE_SITE]

	checks = [
		{
			"check": "site_rows_returned",
			"ok": bool(report_rows),
			"expected": "at least one site row",
			"actual": len(report_rows),
		},
		{
			"check": "lane_site_rollup",
			"ok": len(lane_rows) == 1 and lane_rows[0].get("view_level") == "site",
			"expected": "The Lane MOCKSITE as one rolled-up site row",
			"actual": [
				{
					"project_name": row.get("project_name"),
					"view_level": row.get("view_level"),
					"unit_count": row.get("unit_count"),
				}
				for row in lane_rows
			],
		},
	]

	return {
		"all_passed": all(row["ok"] for row in checks),
		"checks": checks,
		"report_rows": report_rows,
	}


def verify_travel_com_project_actual_timeline_test_data():
	company = _resolve_travel_company()
	site_id = _resolve_travel_lane_site()
	if not site_id:
		frappe.throw("Run seed_travel_com_project_actual_timeline_test_data first.")

	report_rows = _get_report_rows(company, site_id)
	report_names = {row["project_name"] for row in report_rows}
	expected_units = set(PAT_TRAVEL_LANE_UNIT_TIMELINES)

	checks = [
		{
			"check": "lane_units_on_report",
			"ok": expected_units.issubset(report_names),
			"expected": sorted(expected_units),
			"actual": sorted(report_names),
		},
		{
			"check": "ongoing_units_extend_to_today",
			"ok": all(
				cint(row.get("is_ongoing")) == 1
				for row in report_rows
				if row["project_name"] in expected_units and not row.get("actual_end_date")
			),
			"expected": "open units flagged ongoing",
			"actual": [
				(row["project_name"], row.get("is_ongoing"))
				for row in report_rows
				if row["project_name"] in expected_units
			],
		},
		{
			"check": "delayed_unit_present",
			"ok": any(row.get("schedule_status") == "Late" for row in report_rows),
			"expected": "at least one Late row (Unit 1 past expected end, still in progress)",
			"actual": [
				{
					"project": row["project_name"],
					"schedule_status": row.get("schedule_status"),
					"delay_days": row.get("delay_days"),
				}
				for row in report_rows
				if row.get("schedule_status") == "Late"
			],
		},
	]

	return {
		"all_passed": all(row["ok"] for row in checks),
		"checks": checks,
		"report_filters": _travel_report_filters(company, site_id),
		"report_rows": report_rows,
	}


def clear_project_actual_timeline_test_data(site_profile="kitchen.local"):
	"""Clear timeline dates seeded by this module."""
	if site_profile == "travel.com":
		targets = list(PAT_TRAVEL_LANE_UNIT_TIMELINES)
	else:
		targets = [KITCHEN_LOCAL_SITE, *PAT_KITCHEN_LOCAL_UNIT_TIMELINES]

	cleared = []
	for project_name in targets:
		project_id = frappe.db.get_value("Project", {"project_name": project_name}, "name")
		if not project_id:
			project_id = project_name if frappe.db.exists("Project", project_name) else None
		if not project_id:
			continue
		frappe.db.set_value(
			"Project",
			project_id,
			{
				"expected_start_date": None,
				"expected_end_date": None,
				"actual_start_date": None,
				"actual_end_date": None,
			},
			update_modified=False,
		)
		cleared.append(project_id)

	frappe.db.commit()
	return {"cleared": cleared}


def _apply_timeline(project_id, timeline, label=None):
	values = {
		"expected_start_date": timeline.get("expected_start_date"),
		"expected_end_date": timeline.get("expected_end_date"),
		"actual_start_date": timeline.get("actual_start_date"),
		"actual_end_date": timeline.get("actual_end_date"),
		"status": timeline.get("status") or "Open",
	}
	frappe.db.set_value("Project", project_id, values, update_modified=False)
	return {
		"project": project_id,
		"label": label or project_id,
		**values,
	}


def _ensure_kitchen_local_timeline_site(company):
	existing = _resolve_site_by_name(KITCHEN_LOCAL_SITE)
	if existing:
		frappe.db.set_value(
			"Project",
			existing,
			{"project_type": "Site", "company": company, "status": "Open"},
			update_modified=False,
		)
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": KITCHEN_LOCAL_SITE,
			"company": company,
			"project_type": "Site",
			"status": "Open",
			"notes": MARKER,
		}
	)
	_insert_project_doc(doc)
	return doc.name


def _ensure_kitchen_local_unit(site_id, project_name, company):
	existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
	if existing:
		frappe.db.set_value(
			"Project",
			existing,
			{
				"fk_parent_project": site_id,
				"project_type": "Kitchen",
				"company": company,
			},
			update_modified=False,
		)
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": project_name,
			"company": company,
			"project_type": "Kitchen",
			"fk_parent_project": site_id,
			"status": "Open",
			"notes": MARKER,
		}
	)
	_insert_project_doc(doc)
	return doc.name


def _insert_project_doc(doc):
	"""Insert Project without full validate (kitchen.local may lack HRMS tables)."""
	try:
		doc.insert(ignore_permissions=True)
	except Exception:
		doc.db_insert()
		frappe.db.set_value("Project", doc.name, "docstatus", 0, update_modified=False)


def _ensure_lane_kitchen_unit(site_id, project_name, company):
	existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
	if existing:
		frappe.db.set_value(
			"Project",
			existing,
			{
				"fk_parent_project": site_id,
				"project_type": "Kitchen",
				"company": company,
				"status": "Open",
			},
			update_modified=False,
		)
		return existing

	site_customer = frappe.db.get_value("Project", site_id, "customer")
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": project_name,
			"company": company,
			"customer": site_customer,
			"project_type": "Kitchen",
			"fk_parent_project": site_id,
			"status": "Open",
			"notes": MARKER,
		}
	)
	_insert_project_doc(doc)
	return doc.name


def _resolve_site_by_name(project_name):
	return frappe.db.get_value("Project", {"project_name": project_name}, "name")


def _resolve_travel_company():
	for candidate in ("Fitzgerald Kitchens (Demo)", frappe.defaults.get_global_default("company")):
		if candidate and frappe.db.exists("Company", candidate):
			return candidate
	frappe.throw("No company found for travel.com timeline test data.")


def _resolve_travel_lane_site():
	if frappe.db.exists("Project", PAT_TRAVEL_LANE_SITE):
		return PAT_TRAVEL_LANE_SITE
	return frappe.db.get_value(
		"Project",
		{"project_name": PAT_TRAVEL_LANE_SITE_NAME, "project_type": "Site"},
		"name",
	)


def _kitchen_local_report_filters(company, site_id):
	return {
		"company": company,
		**KITCHEN_LOCAL_EXPECTED["filters"],
		"site_project": site_id,
	}


def _travel_report_filters(company, site_id):
	fy_start = getdate(add_to_date(today(), months=-3))
	return {
		"company": company,
		"from_date": fy_start,
		"to_date": getdate(add_to_date(today(), months=3)),
		"site_project": site_id,
	}


def _get_report_rows(company, site_id=None):
	from fitzgerald_kitchens.fitzgerald_kitchens.report.project_actual_timeline.project_actual_timeline import (
		get_data,
	)

	filters = frappe._dict(
		{
			"company": company,
			"from_date": "2026-05-01",
			"to_date": "2026-09-30",
		}
	)
	if site_id:
		filters.site_project = site_id
	return get_data(filters)


def cint(value):
	try:
		return int(value or 0)
	except (TypeError, ValueError):
		return 0
