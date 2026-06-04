# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Demo data for Project Production Time Summary hierarchy testing on kitchen.local.

Creates / refreshes kitchen-local manufacturing fixtures and links unit projects
under a Site parent so selecting the parent in the report shows all child rows.

Run::

    bench --site kitchen.local execute fitzgerald_kitchens.setup.production_time_summary_test_data.insert_production_time_summary_test_data
    bench --site kitchen.local execute fitzgerald_kitchens.setup.production_time_summary_test_data.verify_production_time_summary_test_data
"""

import frappe
from frappe.utils import getdate

from fitzgerald_kitchens.setup.capacity_pipeline_test_data import (
	KITCHEN_LOCAL_EXPECTED,
	KITCHEN_LOCAL_SITE,
	KITCHEN_LOCAL_SITE_EXTRA_CHILD,
	KITCHEN_LOCAL_SITE_LINKED_PROJECTS,
	KITCHEN_LOCAL_STANDALONE_PROJECT,
	_kitchen_local_test_data_exists,
	_resolve_company,
	reset_kitchen_local_delivery_data,
	seed_kitchen_local_test_data,
)


def insert_production_time_summary_test_data():
	"""Seed or refresh demo data for parent/child project report testing."""
	if _kitchen_local_test_data_exists():
		result = reset_kitchen_local_delivery_data()
	else:
		result = seed_kitchen_local_test_data()

	site_id = frappe.db.get_value("Project", {"project_name": KITCHEN_LOCAL_SITE}, "name")
	child_projects = frappe.get_all(
		"Project",
		filters={"parent_project": site_id},
		fields=["name", "project_name"],
		order_by="project_name",
	)
	report_rows = _get_report_rows(site_id, result["company"])
	frappe.db.commit()

	return {
		**result,
		"site": KITCHEN_LOCAL_SITE,
		"site_id": site_id,
		"linked_child_projects": [row.project_name for row in child_projects],
		"standalone_project": KITCHEN_LOCAL_STANDALONE_PROJECT,
		"report_filter_project": site_id,
		"report_filters": {
			"company": result["company"],
			**KITCHEN_LOCAL_EXPECTED["filters"],
			"project": site_id,
		},
		"report_rows": report_rows,
	}


def verify_production_time_summary_test_data():
	"""Verify parent filter returns all linked child projects with manufacturing data."""
	company = _resolve_company()
	site_id = frappe.db.get_value("Project", {"project_name": KITCHEN_LOCAL_SITE}, "name")
	if not site_id:
		frappe.throw(
			f"Site project {KITCHEN_LOCAL_SITE!r} not found. Run insert_production_time_summary_test_data first."
		)

	child_names = set(
		frappe.get_all("Project", filters={"parent_project": site_id}, pluck="project_name")
	)
	expected_children = set(KITCHEN_LOCAL_SITE_LINKED_PROJECTS) | set(KITCHEN_LOCAL_SITE_EXTRA_CHILD)
	report_rows = _get_report_rows(site_id, company)
	report_projects = {row["project_name"] for row in report_rows}

	checks = [
		{
			"check": "site_exists",
			"ok": bool(site_id),
			"expected": KITCHEN_LOCAL_SITE,
			"actual": site_id,
		},
		{
			"check": "linked_children",
			"ok": expected_children.issubset(child_names),
			"expected": sorted(expected_children),
			"actual": sorted(child_names),
		},
		{
			"check": "standalone_not_linked",
			"ok": KITCHEN_LOCAL_STANDALONE_PROJECT not in child_names,
			"expected": f"{KITCHEN_LOCAL_STANDALONE_PROJECT} not under site",
			"actual": sorted(child_names),
		},
		{
			"check": "report_shows_all_linked_children",
			"ok": expected_children.issubset(report_projects),
			"expected": sorted(expected_children),
			"actual": sorted(report_projects),
		},
		{
			"check": "report_excludes_standalone",
			"ok": KITCHEN_LOCAL_STANDALONE_PROJECT not in report_projects,
			"expected": f"{KITCHEN_LOCAL_STANDALONE_PROJECT} excluded when filtering parent",
			"actual": sorted(report_projects),
		},
	]

	return {
		"all_passed": all(row["ok"] for row in checks),
		"checks": checks,
		"report_rows": report_rows,
		"report_filters": {
			"company": company,
			**KITCHEN_LOCAL_EXPECTED["filters"],
			"project": site_id,
		},
	}


def _get_report_rows(site_id, company):
	from fitzgerald_kitchens.fitzgerald_kitchens.report.project_production_time_summary.project_production_time_summary import (
		get_data,
	)

	filters = frappe._dict(
		{
			"company": company,
			**KITCHEN_LOCAL_EXPECTED["filters"],
			"project": site_id,
		}
	)
	return get_data(filters)
