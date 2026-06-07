# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Test data for validating the Capacity Pipeline Report.

Two profiles:

* **kitchen_local** — self-contained small numbers (2 BOMs, capacity 10 & 20,
  5 projects + 1 Site parent, 12 delivery units, June downtime). Use on fresh sites like
  ``kitchen.local``.
* **demo** — overlays delivery dates / units / downtime onto an existing
  Fitzgerald demo site (``travel.com``).

Run::

    bench --site kitchen.local execute fitzgerald_kitchens.setup.capacity_pipeline_test_data.reseed_kitchen_local_capacity_pipeline_test_data
    bench --site kitchen.local execute fitzgerald_kitchens.setup.capacity_pipeline_test_data.verify_all_kitchen_local_capacity_pipeline
"""

import calendar
import re
from datetime import date

import frappe
from frappe.utils import add_to_date, getdate, now_datetime

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

DELIVERY_STAGE = "Kitchen Delivered"
MARKER = "Capacity Pipeline test data"

# ---------------------------------------------------------------------------
# Kitchen-local profile — small predictable numbers
# ---------------------------------------------------------------------------

KITCHEN_LOCAL_WORKSTATION = "Assembly Line - KT"
KITCHEN_LOCAL_TARGET_CAPACITY_A = 10
KITCHEN_LOCAL_TARGET_CAPACITY_B = 20
KITCHEN_LOCAL_REF_YEAR = 2026
KITCHEN_LOCAL_REF_MONTH = 6
KITCHEN_LOCAL_TEST_ITEMS = ("Kitchen Type A - KT", "Kitchen Type B - KT")
KITCHEN_LOCAL_DOWNTIME_JUNE_MINS = 1056  # BOM-A actual Jun capacity 10 -> 9

KITCHEN_LOCAL_PROJECTS = {
	"Alpha Kitchens": (
		"A",
		["2026-06-05", "2026-06-12", "2026-07-08"],
	),
	"Beta Kitchens": (
		"A",
		["2026-06-15", "2026-07-20"],
	),
	"Gamma Kitchens": (
		"B",
		["2026-07-01", "2026-08-10", "2026-08-20"],
	),
}

KITCHEN_LOCAL_SITE = "Riverside Site"
KITCHEN_LOCAL_SITE_LINKED_PROJECTS = ("Alpha Kitchens", "Beta Kitchens")
KITCHEN_LOCAL_SITE_EXTRA_CHILD = {
	"Riverside Kitchen 02": (
		"A",
		["2026-06-25", "2026-08-05"],
	),
	"Riverside Wardrobe 01": (
		"B",
		["2026-06-28", "2026-07-30"],
	),
}
KITCHEN_LOCAL_STANDALONE_PROJECT = "Gamma Kitchens"
KITCHEN_LOCAL_PROJECT_START_DATE = "2026-06-01"

# Unit Qty on each kitchen unit project (1 item = 1 kitchen).
KITCHEN_LOCAL_PROJECT_UNIT_QTY = {
	"Alpha Kitchens": 3,
	"Beta Kitchens": 2,
	"Gamma Kitchens": 1,
	"Riverside Kitchen 02": 2,
}

KITCHEN_LOCAL_EXPECTED = {
	"filters": {
		"from_date": "2026-06-01",
		"to_date": "2026-08-31",
	},
	"pipeline_kpi": {
		"total_demand": 8,
		"total_kitchens": 8,
		"project_count": 4,
	},
	"BOM-A (capacity 10)": {
		"bom_item": "Kitchen Type A - KT",
		"projects": ["Alpha Kitchens", "Beta Kitchens", "Riverside Kitchen 02", "Riverside Site"],
		"months": {
			"Jun '26": {"capacity": "8/10", "demand": 4, "utilisation_pct": 50, "free_capacity": 4},
			"Jul '26": {"capacity": "10/10", "demand": 2, "utilisation_pct": 20, "free_capacity": 8},
			"Aug '26": {"capacity": "9/9", "demand": 1, "utilisation_pct": 11, "free_capacity": 8},
		},
	},
	"BOM-B (capacity 20)": {
		"bom_item": "Kitchen Type B - KT",
		"projects": ["Gamma Kitchens", "Riverside Site", "Riverside Wardrobe 01"],
		"months": {
			"Jun '26": {"capacity": "16/20", "demand": 1, "utilisation_pct": 6, "free_capacity": 15},
			"Jul '26": {"capacity": "20/20", "demand": 2, "utilisation_pct": 10, "free_capacity": 18},
			"Aug '26": {"capacity": "19/19", "demand": 2, "utilisation_pct": 11, "free_capacity": 17},
		},
	},
}

# ---------------------------------------------------------------------------
# Demo profile — travel.com overlay
# ---------------------------------------------------------------------------

DEMO_COMPANY = "Fitzgerald Kitchens (Demo)"
DEMO_KITCHEN_BOM = "BOM-BOM-KIT-TYPE-A-SOCIAL-001-001"
DEMO_ROUTING = "Cabinet Manufacturing - Standard"
DEMO_MFG_MARKER = "Capacity Pipeline demo manufacturing"

DEMO_DOWNTIME_BY_MONTH = {
	"2026-06": [200, 800],
	"2026-07": [300],
	"2026-08": [1500],
}

DEMO_DELIVERY_SCHEDULE = {
	"PROJ-0001": [
		"2026-06-05",
		"2026-06-12",
		"2026-06-19",
		"2026-07-08",
		"2026-07-15",
		"2026-08-03",
		"2026-08-17",
		"2026-09-10",
		"2026-10-01",
		"2026-10-15",
		"2026-11-20",
		"2027-01-08",
	],
	"PROJ-0002": [
		"2026-06-10",
		"2026-06-18",
		"2026-07-22",
		"2026-08-08",
		"2026-09-14",
		"2026-10-28",
	],
	"PROJ-0003": [
		"2026-07-05",
		"2026-07-12",
		"2026-08-20",
		"2026-09-25",
		"2026-11-05",
	],
	"PROJ-0004": [
		"2026-06-25",
		"2026-08-30",
		"2026-10-05",
		"2026-12-12",
	],
	"PROJ-0005": [
		"2026-07-18",
		"2026-09-02",
		"2026-11-15",
	],
}


def insert_capacity_pipeline_test_data(profile=None):
	"""Insert test data — auto-detects profile when not specified."""
	profile = profile or _detect_profile()
	if profile == "demo":
		return _insert_demo_test_data()
	return seed_kitchen_local_test_data()


def seed_kitchen_local_test_data():
	"""Create self-contained test data on a fresh or kitchen.local site."""
	company = _resolve_company()
	if _kitchen_local_test_data_exists():
		return reset_kitchen_local_delivery_data()

	return _seed_kitchen_local_fresh(company)


def purge_kitchen_local_capacity_pipeline_test_data():
	"""
	Remove kitchen.local Capacity Pipeline test data only (not the whole site).

	Deletes test projects, development units, job cards, work orders, and downtime.
	"""
	removed_downtime = _remove_kitchen_local_downtime()
	removed_mfg = _remove_kitchen_local_manufacturing_data(all_on_projects=True)
	removed_units = _remove_kitchen_local_development_units()
	removed_projects = _remove_kitchen_local_test_projects()
	frappe.db.commit()
	return {
		"status": "purged",
		"profile": "kitchen_local",
		"company": _resolve_company(),
		"removed_downtime": removed_downtime,
		"removed_units": removed_units,
		"removed_projects": removed_projects,
		"removed_job_cards": removed_mfg.get("job_cards", 0),
		"removed_work_orders": removed_mfg.get("work_orders", 0),
	}


def reseed_kitchen_local_capacity_pipeline_test_data():
	"""Purge test data then insert a full fresh dataset for manual + automated testing."""
	purged = purge_kitchen_local_capacity_pipeline_test_data()
	seeded = _seed_kitchen_local_fresh(_resolve_company())
	return {"purged": purged, "seeded": seeded}


def _seed_kitchen_local_fresh(company):
	_ensure_app_setup()
	refs = _create_kitchen_local_masters(company)
	created_units = _create_kitchen_local_projects_and_units(refs, company)
	site = _ensure_kitchen_local_site_hierarchy(refs, company)
	_sync_kitchen_local_project_delivery_dates()
	_sync_kitchen_local_project_unit_qty()
	job_cards = _create_kitchen_local_job_cards(refs, company)
	downtime = _create_kitchen_local_downtime(refs["workstation"], company)
	frappe.db.commit()
	return _kitchen_local_summary(
		"seeded",
		company,
		created_units=created_units,
		site=site,
		downtime=downtime,
		job_cards=job_cards,
		**refs,
	)


def reset_kitchen_local_delivery_data():
	"""Reset delivery units on kitchen-local test projects to the fixed schedule."""
	company = _resolve_company()
	if not _kitchen_local_test_data_exists():
		frappe.throw(
			"Kitchen-local test BOMs not found. Run insert_capacity_pipeline_test_data first."
		)

	_ensure_app_setup()
	refs = _get_kitchen_local_refs(company)
	_sync_kitchen_local_masters(company, refs)
	removed = _remove_kitchen_local_development_units()
	created = _create_kitchen_local_projects_and_units(refs, company)
	_ensure_kitchen_local_site_hierarchy(refs, company)
	_sync_kitchen_local_project_delivery_dates()
	_sync_kitchen_local_project_unit_qty()
	removed_mfg = _remove_kitchen_local_manufacturing_data()
	job_cards = _create_kitchen_local_job_cards(refs, company)
	frappe.db.commit()
	return _kitchen_local_summary(
		"delivery data reset",
		company,
		removed_units=removed,
		created_units=created,
		removed_job_cards=removed_mfg.get("job_cards", 0),
		removed_work_orders=removed_mfg.get("work_orders", 0),
		job_cards=job_cards,
		**refs,
	)


def show_demand_and_free_capacity():
	"""Return demand / utilisation / free capacity for kitchen-local test BOMs."""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		execute,
	)

	company = _resolve_company()
	months = ["m_2026_06", "m_2026_07", "m_2026_08"]
	month_labels = {"m_2026_06": "Jun '26", "m_2026_07": "Jul '26", "m_2026_08": "Aug '26"}
	boms = {
		label: frappe.db.get_value(
			"BOM", {"item": spec["bom_item"], "docstatus": 1}, "name"
		)
		for label, spec in KITCHEN_LOCAL_EXPECTED.items()
		if label.startswith("BOM-")
	}

	results = {}
	for label, bom in boms.items():
		if not bom:
			continue
		filters = frappe._dict(
			{
				"company": company,
				**KITCHEN_LOCAL_EXPECTED["filters"],
				"bom": bom,
			}
		)
		_cols, data = execute(filters)
		dem = next(r for r in data if r.get("row_type") == "demand")
		free = next(r for r in data if r.get("row_type") == "free")
		cap = next(r for r in data if r.get("row_type") == "capacity")
		projects = [r for r in data if r.get("row_type") == "project"]
		downtime = next(r for r in data if r.get("row_type") == "downtime")

		row = {
			"projects_shown": [p["project"] for p in projects],
			"months": {},
		}
		for mkey in months:
			actual = cap.get(f"{mkey}_actual") or 0
			theoretical = cap.get(f"{mkey}_theoretical") or 0
			demand = dem.get(mkey) or 0
			row["months"][month_labels[mkey]] = {
				"capacity": f"{actual}/{theoretical}",
				"demand": demand,
				"utilisation_pct": dem.get(f"{mkey}_pct") or 0,
				"free_capacity": free.get(mkey) or 0,
				"downtime_mins": downtime.get(mkey) or 0,
			}
		results[label] = row

	return results


def verify_capacity_pipeline_test_data():
	"""Compare kitchen-local report output against expected small-number fixtures."""
	company = _resolve_company()
	refs = _get_kitchen_local_refs(company)
	_sync_kitchen_local_masters(company, refs)

	actual = show_demand_and_free_capacity()
	checks = []

	for bom_label, expected in KITCHEN_LOCAL_EXPECTED.items():
		if not bom_label.startswith("BOM-"):
			continue
		bom_actual = actual.get(bom_label)
		if not bom_actual:
			checks.append({"bom": bom_label, "ok": False, "error": "missing from report output"})
			continue

		for month_label, exp in expected["months"].items():
			got = bom_actual["months"].get(month_label, {})
			for field in ("capacity", "demand", "free_capacity"):
				checks.append(
					{
						"bom": bom_label,
						"month": month_label,
						"field": field,
						"expected": exp[field],
						"actual": got.get(field),
						"ok": exp[field] == got.get(field),
					}
				)
			checks.append(
				{
					"bom": bom_label,
					"month": month_label,
					"field": "utilisation_pct",
					"expected": exp["utilisation_pct"],
					"actual": got.get("utilisation_pct"),
					"ok": int(got.get("utilisation_pct") or 0) == exp["utilisation_pct"],
				}
			)

	return {
		"all_passed": all(c["ok"] for c in checks),
		"checks": checks,
		"actual": actual,
	}


def verify_pipeline_kpi():
	"""Verify Total kitchens in pipeline KPI (unit qty sum, stable when BOM changes)."""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		get_pipeline_totals,
	)

	if _detect_profile() != "kitchen_local":
		frappe.throw("verify_pipeline_kpi requires kitchen.local test data.")

	company = _resolve_company()
	expected = KITCHEN_LOCAL_EXPECTED["pipeline_kpi"]
	filters = frappe._dict({"company": company, **KITCHEN_LOCAL_EXPECTED["filters"]})
	bom_a = frappe.db.get_value(
		"BOM", {"item": KITCHEN_LOCAL_EXPECTED["BOM-A (capacity 10)"]["bom_item"], "docstatus": 1}, "name"
	)
	bom_b = frappe.db.get_value(
		"BOM", {"item": KITCHEN_LOCAL_EXPECTED["BOM-B (capacity 20)"]["bom_item"], "docstatus": 1}, "name"
	)

	results = {
		"no_bom": get_pipeline_totals(filters),
		"bom_a": get_pipeline_totals(frappe._dict({**filters, "bom": bom_a})),
		"bom_b": get_pipeline_totals(frappe._dict({**filters, "bom": bom_b})),
	}
	checks = []
	for label, totals in results.items():
		for field, exp in expected.items():
			actual = totals.get(field)
			if field == "total_demand" and actual is None:
				actual = totals.get("total_kitchens")
			checks.append(
				{
					"filter": label,
					"field": field,
					"expected": exp,
					"actual": actual,
					"ok": actual == exp,
				}
			)
	bom_stable = results["no_bom"] == results["bom_a"] == results["bom_b"]
	return {
		"all_passed": all(c["ok"] for c in checks) and bom_stable,
		"bom_independent": bom_stable,
		"checks": checks,
		"results": results,
	}


def verify_all_kitchen_local_capacity_pipeline():
	"""Run all automated Capacity Pipeline checks on kitchen.local."""
	capacity_report = verify_capacity_pipeline_test_data()
	project_item_counts = verify_project_item_counts()
	pipeline_kpi = verify_pipeline_kpi()
	return {
		"all_passed": (
			capacity_report.get("all_passed")
			and project_item_counts.get("all_passed")
			and pipeline_kpi.get("all_passed")
		),
		"capacity_report": capacity_report,
		"project_item_counts": project_item_counts,
		"pipeline_kpi": pipeline_kpi,
	}


def verify_project_item_counts():
	"""
	Audit each Capacity Pipeline project row on kitchen.local:

	- Monthly cell totals vs subtitle (Site rows)
	- Kitchen / robe tooltip totals vs subtitle
	- Raw Project delivery counts in the report horizon
	"""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		execute,
	)

	if _detect_profile() != "kitchen_local":
		frappe.throw("verify_project_item_counts requires kitchen.local test data.")

	company = _resolve_company()
	month_keys = ["m_2026_06", "m_2026_07", "m_2026_08"]
	filters_base = frappe._dict({"company": company, **KITCHEN_LOCAL_EXPECTED["filters"]})

	bom_specs = {
		label: frappe.db.get_value("BOM", {"item": spec["bom_item"], "docstatus": 1}, "name")
		for label, spec in KITCHEN_LOCAL_EXPECTED.items()
		if label.startswith("BOM-")
	}

	audits = []
	for bom_label, bom in bom_specs.items():
		if not bom:
			continue
		filters = frappe._dict({**filters_base, "bom": bom})
		_cols, data = execute(filters)
		project_rows = [r for r in data if r.get("row_type") == "project"]

		for row in project_rows:
			audit = _audit_project_row(row, month_keys, filters)
			audit["bom_filter"] = bom_label
			audits.append(audit)

	db_counts = _kitchen_local_db_unit_counts(filters_base["from_date"], filters_base["to_date"])

	return {
		"all_passed": all(a["subtitle_matches_monthly"] for a in audits if a["project_type"] == "Site"),
		"audits": audits,
		"db_delivery_counts_by_project": db_counts,
	}


def _parse_site_subtitle(subtitle):
	"""Return (units, kitchens, wardrobes) parsed from a Site subtitle string."""
	units = kitchens = wardrobes = 0
	if not subtitle:
		return units, kitchens, wardrobes
	match = re.search(r"^(\d+)\s+Units?\b", subtitle, re.IGNORECASE)
	if match:
		units = int(match.group(1))
	match = re.search(r"(\d+)\s+kitchens", subtitle, re.IGNORECASE)
	if match:
		kitchens = int(match.group(1))
	match = re.search(r"(\d+)\s+Wardrobes?", subtitle, re.IGNORECASE)
	if match:
		wardrobes = int(match.group(1))
	return units, kitchens, wardrobes


def _expected_site_subtitle_counts(site_project_id):
	"""Structural child counts under a Site (fallback when no demand in horizon)."""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		_query_site_structural_totals,
	)

	totals = _query_site_structural_totals(site_project_id)
	return {
		"units": totals["kitchens"],
		"kitchens": totals["kitchens"],
		"wardrobes": totals["wardrobes"],
	}


def _audit_project_row(row, month_keys, filters):
	project_id = row.get("project_id")
	project_type = frappe.db.get_value("Project", project_id, "project_type") if project_id else None

	monthly = {}
	sum_demand = sum_kitchen = sum_robe = 0
	for mkey in month_keys:
		demand = int(row.get(mkey) or 0)
		kitchen = int(row.get(f"{mkey}_kitchen") or 0)
		robe = int(row.get(f"{mkey}_wardrobe") or 0)
		monthly[mkey] = {"demand": demand, "kitchen": kitchen, "robe": robe}
		sum_demand += demand
		sum_kitchen += kitchen
		sum_robe += robe

	sub_units, sub_kitchen, sub_robe = _parse_site_subtitle(row.get("subtitle") or "")

	subtitle_matches = True
	if project_type == "Site":
		subtitle_matches = (
			sub_units == sum_kitchen
			and sub_kitchen == sum_kitchen
			and sub_robe == sum_robe
		)

	return {
		"project": row.get("project"),
		"project_id": project_id,
		"project_type": project_type,
		"subtitle": row.get("subtitle") or "",
		"monthly": monthly,
		"sum_demand": sum_demand,
		"sum_kitchen": sum_kitchen,
		"sum_robe": sum_robe,
		"subtitle_units": sub_units,
		"subtitle_kitchens": sub_kitchen,
		"subtitle_robes": sub_robe,
		"subtitle_matches_monthly": subtitle_matches,
	}


def _kitchen_local_db_unit_counts(from_date, to_date):
	"""Project scheduled delivery counts per project (report horizon)."""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		_project_is_kitchen_sql,
		_project_is_wardrobe_sql,
		_project_schedule_date_sql,
		_project_unit_qty_sql,
	)

	schedule = _project_schedule_date_sql("p")
	qty = _project_unit_qty_sql("p")
	kitchen = _project_is_kitchen_sql("p")
	wardrobe = _project_is_wardrobe_sql("p")
	rows = frappe.db.sql(
		f"""
		SELECT
			p.project_name,
			p.project_type,
			DATE_FORMAT({schedule}, '%%Y-%%m') AS ym,
			SUM({qty}) AS units,
			SUM(CASE WHEN {kitchen} THEN {qty} ELSE 0 END) AS kitchens,
			SUM(CASE WHEN {wardrobe} THEN {qty} ELSE 0 END) AS robes
		FROM
			`tabProject` p
		WHERE
			IFNULL(p.project_type, '') != 'Site'
			AND {schedule} BETWEEN %(from_date)s AND %(to_date)s
			AND p.project_name IN %(names)s
		GROUP BY
			p.project_name, p.project_type, ym
		ORDER BY
			p.project_name, ym
		""",
		{
			"from_date": from_date,
			"to_date": to_date,
			"names": _kitchen_local_manufacturing_project_names()
			+ [KITCHEN_LOCAL_SITE],
		},
		as_dict=True,
	)

	by_project = {}
	for row in rows:
		entry = by_project.setdefault(
			row.project_name,
			{"project_type": row.project_type, "months": {}, "total": 0, "kitchens": 0, "robes": 0},
		)
		entry["months"][row.ym] = {
			"units": int(row.units),
			"kitchens": int(row.kitchens or 0),
			"robes": int(row.robes or 0),
		}
		entry["total"] += int(row.units)
		entry["kitchens"] += int(row.kitchens or 0)
		entry["robes"] += int(row.robes or 0)

	return by_project


# ---------------------------------------------------------------------------
# Profile detection
# ---------------------------------------------------------------------------

def _detect_profile():
	if frappe.db.exists("BOM", DEMO_KITCHEN_BOM):
		return "demo"
	return "kitchen_local"


# ---------------------------------------------------------------------------
# Kitchen-local helpers
# ---------------------------------------------------------------------------

def _kitchen_local_manufacturing_projects():
	projects = dict(KITCHEN_LOCAL_PROJECTS)
	projects.update(KITCHEN_LOCAL_SITE_EXTRA_CHILD)
	return projects


def _kitchen_local_manufacturing_project_names():
	return list(_kitchen_local_manufacturing_projects().keys())


def _all_kitchen_local_project_names():
	names = list(_kitchen_local_manufacturing_projects().keys())
	if KITCHEN_LOCAL_SITE not in names:
		names.append(KITCHEN_LOCAL_SITE)
	return names


def _kitchen_local_test_data_exists():
	return bool(
		frappe.db.get_value("BOM", {"item": KITCHEN_LOCAL_TEST_ITEMS[0], "docstatus": 1}, "name")
		and frappe.db.exists(
			"Project", {"project_name": ["in", list(KITCHEN_LOCAL_PROJECTS.keys())]}
		)
	)


def _kitchen_local_summary(status, company, **extra):
	out = {
		"status": status,
		"profile": "kitchen_local",
		"company": company,
		"bom_a_capacity_target": KITCHEN_LOCAL_TARGET_CAPACITY_A,
		"bom_b_capacity_target": KITCHEN_LOCAL_TARGET_CAPACITY_B,
		"projects": list(KITCHEN_LOCAL_PROJECTS.keys()),
		"expected": KITCHEN_LOCAL_EXPECTED,
	}
	out.update(extra)
	return out


def _get_kitchen_local_refs(company):
	bom_a = frappe.db.get_value(
		"BOM", {"item": KITCHEN_LOCAL_TEST_ITEMS[0], "docstatus": 1}, "name"
	)
	bom_b = frappe.db.get_value(
		"BOM", {"item": KITCHEN_LOCAL_TEST_ITEMS[1], "docstatus": 1}, "name"
	)
	if not bom_a or not bom_b:
		frappe.throw("Kitchen-local test BOMs missing. Re-run insert_capacity_pipeline_test_data.")

	return {
		"customer": _get_or_create_kitchen_local_customer(),
		"workstation": KITCHEN_LOCAL_WORKSTATION,
		"bom_a": bom_a,
		"bom_b": bom_b,
	}


def _remove_kitchen_local_development_units():
	project_names = _all_kitchen_local_project_names()
	projects = frappe.get_all(
		"Project", filters={"project_name": ["in", project_names]}, pluck="name"
	)
	if not projects:
		return 0

	units = frappe.get_all(
		"Development Unit", filters={"project": ["in", projects]}, pluck="name"
	)
	for name in units:
		frappe.delete_doc("Development Unit", name, ignore_permissions=True, force=True)

	return len(units)


def _weekdays_in_month(year, month):
	return sum(
		1
		for day in range(1, calendar.monthrange(year, month)[1] + 1)
		if date(year, month, day).weekday() < 5
	)


def _operation_time_for_capacity(target_capacity):
	weekdays = _weekdays_in_month(KITCHEN_LOCAL_REF_YEAR, KITCHEN_LOCAL_REF_MONTH)
	available_mins = 1 * weekdays * 8 * 60
	return int(available_mins / target_capacity)


def _create_kitchen_local_masters(company):
	customer = _get_or_create_kitchen_local_customer()
	workstation = _get_or_create_kitchen_local_workstation()
	time_a = _operation_time_for_capacity(KITCHEN_LOCAL_TARGET_CAPACITY_A)
	time_b = _operation_time_for_capacity(KITCHEN_LOCAL_TARGET_CAPACITY_B)

	item_a = _get_or_create_kitchen_local_item("Kitchen Type A - KT", "Kitchen end product A")
	item_b = _get_or_create_kitchen_local_item("Kitchen Type B - KT", "Kitchen end product B")
	raw_item = _get_or_create_kitchen_local_item("Board Material - KT", "Raw board", is_raw=1)

	routing_a = _get_or_create_kitchen_local_routing(
		"Capacity Test Routing A", "Assembly Op A", workstation, time_a
	)
	routing_b = _get_or_create_kitchen_local_routing(
		"Capacity Test Routing B", "Assembly Op B", workstation, time_b
	)

	bom_a = _get_or_create_kitchen_local_bom(item_a, routing_a, raw_item, qty=2, company=company)
	bom_b = _get_or_create_kitchen_local_bom(item_b, routing_b, raw_item, qty=3, company=company)

	return {
		"customer": customer,
		"workstation": workstation,
		"bom_a": bom_a,
		"bom_b": bom_b,
		"time_a_mins": time_a,
		"time_b_mins": time_b,
	}


def _sync_kitchen_local_masters(company, refs):
	"""Re-apply workstation / routing settings so capacity stays predictable."""
	_get_or_create_kitchen_local_workstation()
	time_a = _operation_time_for_capacity(KITCHEN_LOCAL_TARGET_CAPACITY_A)
	time_b = _operation_time_for_capacity(KITCHEN_LOCAL_TARGET_CAPACITY_B)
	_get_or_create_kitchen_local_routing(
		"Capacity Test Routing A", "Assembly Op A", refs["workstation"], time_a
	)
	_get_or_create_kitchen_local_routing(
		"Capacity Test Routing B", "Assembly Op B", refs["workstation"], time_b
	)
	for bom in (refs["bom_a"], refs["bom_b"]):
		frappe.db.set_value("BOM", bom, "description", MARKER, update_modified=False)


def _get_or_create_kitchen_local_customer():
	from frappe.utils.nestedset import get_root_of

	name = "Test Customer - KT"
	if frappe.db.exists("Customer", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"customer_group": get_root_of("Customer Group"),
			"territory": get_root_of("Territory"),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_kitchen_local_workstation():
	if frappe.db.exists("Workstation", KITCHEN_LOCAL_WORKSTATION):
		frappe.db.set_value(
			"Workstation",
			KITCHEN_LOCAL_WORKSTATION,
			{
				"production_capacity": 1,
				"total_working_hours": 8,
				"holiday_list": "",
			},
			update_modified=False,
		)
		return KITCHEN_LOCAL_WORKSTATION

	doc = frappe.get_doc(
		{
			"doctype": "Workstation",
			"workstation_name": KITCHEN_LOCAL_WORKSTATION,
			"production_capacity": 1,
			"total_working_hours": 8,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_kitchen_local_item(item_code, description, is_raw=0):
	if frappe.db.exists("Item", item_code):
		return item_code

	from frappe.utils.nestedset import get_root_of

	item_group = get_root_of("Item Group")
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"include_item_in_manufacturing": 1,
			"description": description,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_kitchen_local_operation(operation_name):
	if frappe.db.exists("Operation", operation_name):
		return operation_name

	doc = frappe.get_doc({"doctype": "Operation", "name": operation_name})
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_kitchen_local_routing(routing_name, operation_name, workstation, time_in_mins):
	if frappe.db.exists("Routing", routing_name):
		frappe.db.sql(
			"""
			UPDATE `tabBOM Operation`
			SET time_in_mins = %s, workstation = %s
			WHERE parent = %s
			""",
			(time_in_mins, workstation, routing_name),
		)
		return routing_name

	operation = _get_or_create_kitchen_local_operation(operation_name)
	doc = frappe.get_doc(
		{
			"doctype": "Routing",
			"routing_name": routing_name,
			"operations": [
				{
					"operation": operation,
					"workstation": workstation,
					"time_in_mins": time_in_mins,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_kitchen_local_bom(item, routing, raw_item, qty, company):
	existing = frappe.db.get_value("BOM", {"item": item, "docstatus": 1, "is_active": 1}, "name")
	if existing:
		frappe.db.set_value("BOM", existing, "description", MARKER, update_modified=False)
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": item,
			"company": company,
			"quantity": 1,
			"is_active": 1,
			"with_operations": 1,
			"routing": routing,
			"description": MARKER,
			"items": [{"item_code": raw_item, "qty": qty, "uom": "Nos"}],
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _create_kitchen_local_projects_and_units(refs, company):
	bom_map = {"A": refs["bom_a"], "B": refs["bom_b"]}
	created_units = 0

	for project_name, (bom_key, dates) in KITCHEN_LOCAL_PROJECTS.items():
		project = _get_or_create_kitchen_local_project(
			project_name,
			bom_map[bom_key],
			refs["customer"],
			company,
			expected_end_date=dates[0] if dates else None,
		)
		for index, planned_date in enumerate(dates, start=1):
			unit = frappe.get_doc(
				{
					"doctype": "Development Unit",
					"naming_series": "DU-.YYYY.-.#####",
					"unit_reference": f"{project_name} Unit {index:02d}",
					"project": project,
					"customer": refs["customer"],
				}
			)
			unit.insert(ignore_permissions=True)
			_set_delivery_planned_date(unit.name, planned_date)
			created_units += 1

	return created_units


def _get_or_create_kitchen_local_project(
	project_name,
	kitchen_bom,
	customer,
	company,
	project_type=None,
	site_parent=None,
	expected_end_date=None,
):
	existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
	resolved_type = project_type or "Kitchen"

	if existing:
		update_values = {
			"fk_effective_bom": kitchen_bom,
			"project_type": resolved_type,
			"customer": customer,
			"company": company,
		}
		if site_parent is not None:
			update_values["fk_parent_project"] = site_parent
		if expected_end_date:
			update_values["expected_end_date"] = expected_end_date
		frappe.db.set_value(
			"Project",
			existing,
			update_values,
			update_modified=False,
		)
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": project_name,
			"company": company,
			"customer": customer,
			"fk_effective_bom": kitchen_bom,
			"project_type": resolved_type,
			"status": "Open",
			"expected_start_date": KITCHEN_LOCAL_PROJECT_START_DATE,
			**({"expected_end_date": expected_end_date} if expected_end_date else {}),
			**({"fk_parent_project": site_parent} if site_parent else {}),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _sync_kitchen_local_project_delivery_dates():
	"""Set Project expected_end_date from the first scheduled delivery in test fixtures."""
	for mapping in (KITCHEN_LOCAL_PROJECTS, KITCHEN_LOCAL_SITE_EXTRA_CHILD):
		for project_name, (_bom_key, dates) in mapping.items():
			if not dates:
				continue
			project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
			if not project:
				continue
			frappe.db.set_value(
				"Project",
				project,
				{"expected_end_date": dates[0], "expected_start_date": KITCHEN_LOCAL_PROJECT_START_DATE},
				update_modified=False,
			)


def _sync_kitchen_local_project_unit_qty():
	"""Set fk_unit_qty on kitchen unit projects (1 item = 1 kitchen)."""
	if not frappe.db.has_column("Project", "fk_unit_qty"):
		return

	for project_name, qty in KITCHEN_LOCAL_PROJECT_UNIT_QTY.items():
		project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
		if not project:
			continue
		frappe.db.set_value(
			"Project",
			project,
			"fk_unit_qty",
			qty,
			update_modified=False,
		)


def _sync_kitchen_local_project_creation_dates():
	"""Deprecated — KPI uses planned delivery dates and fk_unit_qty."""
	return None


def _get_or_create_kitchen_local_site_project(refs, company):
	existing = frappe.db.get_value("Project", {"project_name": KITCHEN_LOCAL_SITE}, "name")
	values = {
		"project_type": "Site",
		"customer": refs["customer"],
		"company": company,
		"status": "Open",
	}
	if existing:
		frappe.db.set_value("Project", existing, values, update_modified=False)
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": KITCHEN_LOCAL_SITE,
			**values,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_kitchen_local_site_hierarchy(refs, company):
	"""Link kitchen unit projects under a Site parent for hierarchy report testing."""
	from fitzgerald_kitchens.setup.project_types import ensure_project_types

	ensure_project_types()
	site = _get_or_create_kitchen_local_site_project(refs, company)
	bom_map = {"A": refs["bom_a"], "B": refs["bom_b"]}
	created_units = 0

	for project_name in KITCHEN_LOCAL_SITE_LINKED_PROJECTS:
		project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
		if not project:
			continue
		frappe.db.set_value(
			"Project",
			project,
			{
				"fk_parent_project": site,
				"project_type": "Kitchen",
				"expected_start_date": KITCHEN_LOCAL_PROJECT_START_DATE,
			},
			update_modified=False,
		)

	for project_name, (bom_key, dates) in KITCHEN_LOCAL_SITE_EXTRA_CHILD.items():
		project_type = "Robe" if "Wardrobe" in project_name else "Kitchen"
		project = _get_or_create_kitchen_local_project(
			project_name,
			bom_map[bom_key],
			refs["customer"],
			company,
			project_type=project_type,
			site_parent=site,
			expected_end_date=dates[0] if dates else None,
		)
		for index, planned_date in enumerate(dates, start=1):
			unit_reference = f"{project_name} Unit {index:02d}"
			if frappe.db.exists(
				"Development Unit", {"unit_reference": unit_reference, "project": project}
			):
				_set_delivery_planned_date(
					frappe.db.get_value(
						"Development Unit",
						{"unit_reference": unit_reference, "project": project},
						"name",
					),
					planned_date,
				)
				continue

			unit = frappe.get_doc(
				{
					"doctype": "Development Unit",
					"naming_series": "DU-.YYYY.-.#####",
					"unit_reference": unit_reference,
					"project": project,
					"customer": refs["customer"],
					"kitchen_required": 1,
					"kitchen_bom": bom_map[bom_key],
				}
			)
			unit.insert(ignore_permissions=True)
			_set_delivery_planned_date(unit.name, planned_date)
			created_units += 1

	standalone = frappe.db.get_value(
		"Project", {"project_name": KITCHEN_LOCAL_STANDALONE_PROJECT}, "name"
	)
	if standalone:
		frappe.db.set_value(
			"Project",
			standalone,
			{
				"fk_parent_project": None,
				"project_type": "Kitchen",
				"expected_start_date": KITCHEN_LOCAL_PROJECT_START_DATE,
			},
			update_modified=False,
		)

	return {"site": site, "created_units": created_units}


def _create_kitchen_local_downtime(workstation, company):
	_remove_kitchen_local_downtime()

	employee = _get_or_create_kitchen_local_employee(company)
	from_time = f"{KITCHEN_LOCAL_REF_YEAR}-{KITCHEN_LOCAL_REF_MONTH:02d}-03 08:00:00"
	to_time = add_to_date(from_time, minutes=KITCHEN_LOCAL_DOWNTIME_JUNE_MINS)

	doc = frappe.get_doc(
		{
			"doctype": "Downtime Entry",
			"naming_series": "DT-",
			"workstation": workstation,
			"operator": employee,
			"from_time": from_time,
			"to_time": to_time,
			"stop_reason": "Machine malfunction",
			"remarks": MARKER,
		}
	)
	doc.insert(ignore_permissions=True)
	return 1


def _get_kitchen_local_warehouses(company):
	warehouse = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "disabled": 0}, "name"
	)
	if not warehouse:
		frappe.throw(f"No warehouse found for company {company}. Complete ERPNext setup first.")
	return warehouse


def _remove_kitchen_local_downtime():
	names = frappe.get_all("Downtime Entry", filters={"remarks": MARKER}, pluck="name")
	for name in names:
		doc = frappe.get_doc("Downtime Entry", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Downtime Entry", name, ignore_permissions=True, force=True)
	return len(names)


def _remove_kitchen_local_test_projects():
	removed = []
	for project_name in _all_kitchen_local_project_names():
		if project_name == KITCHEN_LOCAL_SITE:
			continue
		if _delete_project_by_name(project_name):
			removed.append(project_name)
	if _delete_project_by_name(KITCHEN_LOCAL_SITE):
		removed.append(KITCHEN_LOCAL_SITE)
	return removed


def _delete_project_by_name(project_name):
	project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
	if not project:
		return False

	for child in frappe.get_all("Project", filters={"fk_parent_project": project}, pluck="name"):
		frappe.db.set_value("Project", child, "fk_parent_project", None, update_modified=False)

	for unit in frappe.get_all("Development Unit", filters={"project": project}, pluck="name"):
		frappe.delete_doc("Development Unit", unit, ignore_permissions=True, force=True)

	doc = frappe.get_doc("Project", project)
	if doc.docstatus == 1:
		doc.cancel()
	frappe.delete_doc("Project", project, ignore_permissions=True, force=True)
	return True


def _remove_kitchen_local_manufacturing_data(all_on_projects=False):
	project_names = _all_kitchen_local_project_names()
	projects = frappe.get_all(
		"Project", filters={"project_name": ["in", project_names]}, pluck="name"
	)
	if not projects:
		return {"job_cards": 0, "work_orders": 0}

	removed_jc = 0
	wo_names = set()
	jc_filters = {"project": ["in", projects]}
	if not all_on_projects:
		jc_filters["remarks"] = MARKER
	for name in frappe.get_all("Job Card", filters=jc_filters, pluck="name"):
		work_order = frappe.db.get_value("Job Card", name, "work_order")
		if work_order:
			wo_names.add(work_order)
		doc = frappe.get_doc("Job Card", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Job Card", name, ignore_permissions=True, force=True)
		removed_jc += 1

	for row in frappe.get_all(
		"Work Order",
		filters={
			"project": ["in", projects],
			"production_item": ["in", list(KITCHEN_LOCAL_TEST_ITEMS)],
		},
		fields=["name"],
	):
		wo_names.add(row.name)

	removed_wo = 0
	for name in wo_names:
		if not frappe.db.exists("Work Order", name):
			continue
		doc = frappe.get_doc("Work Order", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Work Order", name, ignore_permissions=True, force=True)
		removed_wo += 1

	return {"job_cards": removed_jc, "work_orders": removed_wo}


def _create_kitchen_local_job_cards(refs, company):
	"""Create submitted job cards with monthly time logs for demand calculation."""
	_remove_kitchen_local_manufacturing_data()
	warehouse = _get_kitchen_local_warehouses(company)
	created = 0

	for project_name, (bom_key, dates) in _kitchen_local_manufacturing_projects().items():
		project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
		bom = refs["bom_a"] if bom_key == "A" else refs["bom_b"]
		item = frappe.db.get_value("BOM", bom, "item")
		target = KITCHEN_LOCAL_TARGET_CAPACITY_A if bom_key == "A" else KITCHEN_LOCAL_TARGET_CAPACITY_B
		op_time = _operation_time_for_capacity(target)

		wo = frappe.new_doc("Work Order")
		wo.production_item = item
		wo.bom_no = bom
		wo.qty = len(dates)
		wo.company = company
		wo.project = project
		wo.fg_warehouse = warehouse
		wo.wip_warehouse = warehouse
		wo.skip_transfer = 1
		wo.get_items_and_operations_from_bom()
		wo.insert(ignore_permissions=True)
		wo.submit()

		job_card_names = frappe.get_all(
			"Job Card",
			filters={"work_order": wo.name, "workstation": KITCHEN_LOCAL_WORKSTATION},
			pluck="name",
		)
		if not job_card_names:
			continue

		jc = frappe.get_doc("Job Card", job_card_names[0])
		jc.remarks = MARKER
		for planned_date in dates:
			from_time = f"{planned_date} 08:00:00"
			jc.append(
				"time_logs",
				{
					"from_time": from_time,
					"to_time": add_to_date(from_time, minutes=op_time),
					"time_in_mins": op_time,
					"completed_qty": 1,
				},
			)
		jc.save(ignore_permissions=True)
		if jc.docstatus == 0:
			jc.submit()
		created += 1

	return created


def _get_or_create_kitchen_local_employee(company):
	name = frappe.db.get_value("Employee", {"status": "Active", "company": company}, "name")
	if name:
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Test",
			"last_name": "Operator",
			"employee_name": "Test Operator",
			"company": company,
			"status": "Active",
			"date_of_birth": "1990-01-01",
			"date_of_joining": now_datetime().date(),
			"gender": "Male",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------------------
# Demo-site helpers
# ---------------------------------------------------------------------------

def _insert_demo_test_data():
	"""Populate demo site with delivery dates, job cards, and BOM routing for report testing."""
	_ensure_app_setup()
	_enable_demo_bom_capacity()
	_set_demo_project_kitchen_boms()
	updated = _update_demo_existing_delivery_dates()
	created = _create_demo_development_units()
	removed_mfg = _remove_demo_manufacturing_data()
	job_cards = _create_demo_job_cards()
	downtime_created = _create_demo_downtime_entries()
	frappe.db.commit()

	return {
		"profile": "demo",
		"bom_updated": DEMO_KITCHEN_BOM,
		"projects_updated": len(DEMO_DELIVERY_SCHEDULE),
		"delivery_dates_updated": updated,
		"development_units_created": created,
		"removed_job_cards": removed_mfg.get("job_cards", 0),
		"removed_work_orders": removed_mfg.get("work_orders", 0),
		"job_cards_created": job_cards,
		"downtime_entries_created": downtime_created,
	}


def _enable_demo_bom_capacity():
	if not frappe.db.exists("BOM", DEMO_KITCHEN_BOM):
		frappe.throw(f"BOM {DEMO_KITCHEN_BOM} not found")

	frappe.db.set_value(
		"BOM",
		DEMO_KITCHEN_BOM,
		{
			"routing": DEMO_ROUTING,
			"with_operations": 1,
		},
		update_modified=True,
	)


def _set_demo_project_kitchen_boms():
	for project, dates in DEMO_DELIVERY_SCHEDULE.items():
		if not frappe.db.exists("Project", project):
			continue

		values = {
			"fk_effective_bom": DEMO_KITCHEN_BOM,
			"kitchen_bom": DEMO_KITCHEN_BOM,
			"kitchen_required": 1,
			"project_type": "Kitchen",
		}
		if dates:
			values["expected_end_date"] = dates[0]

		frappe.db.set_value(
			"Project",
			project,
			values,
			update_modified=False,
		)


def _update_demo_existing_delivery_dates():
	count = 0
	for project, dates in DEMO_DELIVERY_SCHEDULE.items():
		existing_units = frappe.get_all(
			"Development Unit",
			filters={"project": project},
			pluck="name",
			order_by="creation asc",
		)
		if not existing_units:
			continue

		for unit_name, planned_date in zip(existing_units, dates):
			_set_delivery_planned_date(unit_name, planned_date)
			count += 1

	return count


def _create_demo_development_units():
	created = 0
	for project, dates in DEMO_DELIVERY_SCHEDULE.items():
		if not frappe.db.exists("Project", project):
			continue

		existing_count = frappe.db.count("Development Unit", {"project": project})
		dates_to_create = dates[existing_count:]
		if not dates_to_create:
			continue

		project_name = frappe.db.get_value("Project", project, "project_name") or project
		for index, planned_date in enumerate(dates_to_create, start=existing_count + 1):
			unit_reference = f"{project_name} Unit {index:03d}"
			doc = frappe.get_doc(
				{
					"doctype": "Development Unit",
					"naming_series": "DU-.YYYY.-.#####",
					"unit_reference": unit_reference,
					"project": project,
					"company": DEMO_COMPANY,
					"customer": _get_demo_project_customer(project),
				}
			)
			doc.insert(ignore_permissions=True)
			_set_delivery_planned_date(doc.name, planned_date)
			created += 1

	return created


def _get_demo_project_customer(project):
	customer = frappe.db.get_value("Project", project, "customer")
	if customer:
		return customer

	return frappe.db.get_value("Customer", {"disabled": 0}, "name") or "Grant Plastics Ltd."


def _get_demo_bottleneck():
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		_get_bottleneck_operation,
		_q_bom_operations,
	)

	return _get_bottleneck_operation(_q_bom_operations([DEMO_KITCHEN_BOM]))


def _get_demo_workstation(bottleneck):
	if bottleneck.workstation:
		return bottleneck.workstation

	if bottleneck.workstation_type:
		workstation = frappe.db.get_value(
			"Workstation",
			{"workstation_type": bottleneck.workstation_type, "disabled": 0},
			"name",
		)
		if workstation:
			return workstation

	return frappe.db.get_value("Workstation", {"disabled": 0}, "name")


def _get_demo_warehouse():
	warehouse = frappe.db.get_value(
		"Warehouse",
		{"company": DEMO_COMPANY, "is_group": 0, "disabled": 0},
		"name",
	)
	if not warehouse:
		frappe.throw(f"No warehouse found for {DEMO_COMPANY}")
	return warehouse


def _remove_demo_manufacturing_data():
	projects = list(DEMO_DELIVERY_SCHEDULE.keys())
	production_item = frappe.db.get_value("BOM", DEMO_KITCHEN_BOM, "item")

	removed_jc = 0
	wo_names = set()
	for name in frappe.get_all(
		"Job Card", filters={"project": ["in", projects], "remarks": DEMO_MFG_MARKER}, pluck="name"
	):
		work_order = frappe.db.get_value("Job Card", name, "work_order")
		if work_order:
			wo_names.add(work_order)
		doc = frappe.get_doc("Job Card", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Job Card", name, ignore_permissions=True, force=True)
		removed_jc += 1

	if production_item:
		for row in frappe.get_all(
			"Work Order",
			filters={"project": ["in", projects], "production_item": production_item},
			fields=["name"],
		):
			wo_names.add(row.name)

	removed_wo = 0
	for name in wo_names:
		if not frappe.db.exists("Work Order", name):
			continue
		doc = frappe.get_doc("Work Order", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Work Order", name, ignore_permissions=True, force=True)
		removed_wo += 1

	return {"job_cards": removed_jc, "work_orders": removed_wo}


def _create_demo_job_cards():
	"""Create work orders and job cards with monthly actual time on the bottleneck operation."""
	bottleneck = _get_demo_bottleneck()
	if not bottleneck:
		return 0

	_remove_demo_manufacturing_data()

	warehouse = _get_demo_warehouse()
	workstation = _get_demo_workstation(bottleneck)
	production_item = frappe.db.get_value("BOM", DEMO_KITCHEN_BOM, "item")
	op_time = int(bottleneck.time_in_mins)
	created = 0

	for project, dates in DEMO_DELIVERY_SCHEDULE.items():
		if not frappe.db.exists("Project", project) or not dates:
			continue

		wo = frappe.new_doc("Work Order")
		wo.production_item = production_item
		wo.bom_no = DEMO_KITCHEN_BOM
		wo.qty = len(dates)
		wo.company = DEMO_COMPANY
		wo.project = project
		wo.fg_warehouse = warehouse
		wo.wip_warehouse = warehouse
		wo.skip_transfer = 1
		wo.get_items_and_operations_from_bom()
		wo.insert(ignore_permissions=True)
		wo.submit()

		jc = frappe.new_doc("Job Card")
		jc.work_order = wo.name
		jc.company = DEMO_COMPANY
		jc.project = project
		jc.bom_no = DEMO_KITCHEN_BOM
		jc.production_item = production_item
		jc.operation = bottleneck.operation
		jc.workstation = workstation
		if bottleneck.workstation_type:
			jc.workstation_type = bottleneck.workstation_type
		jc.for_quantity = len(dates)
		jc.wip_warehouse = warehouse
		jc.posting_date = getdate(dates[0])
		jc.remarks = DEMO_MFG_MARKER

		for planned_date in dates:
			from_time = f"{planned_date} 08:00:00"
			jc.append(
				"time_logs",
				{
					"from_time": from_time,
					"to_time": add_to_date(from_time, minutes=op_time),
					"time_in_mins": op_time,
					"completed_qty": 1,
				},
			)

		jc.insert(ignore_permissions=True)
		jc.submit()
		created += 1

	return created


def _create_demo_downtime_entries():
	"""Insert Downtime Entry records on the bottleneck workstation for demo months."""
	if frappe.db.exists(
		"Downtime Entry",
		{"remarks": ("like", "Capacity pipeline demo downtime%")},
	):
		return 0

	workstation = frappe.db.get_value(
		"Workstation", {"workstation_name": ("like", "%Edge Bander%")}, "name"
	) or frappe.db.get_value("Workstation", {"disabled": 0}, "name")

	if not workstation:
		return 0

	operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if not operator:
		return 0

	created = 0
	for ym, durations in DEMO_DOWNTIME_BY_MONTH.items():
		year, month = ym.split("-")
		for index, mins in enumerate(durations, start=1):
			day = min(index + 1, 28)
			from_time = f"{year}-{month}-{day:02d} 08:00:00"
			to_time = add_to_date(from_time, minutes=int(mins))

			doc = frappe.get_doc(
				{
					"doctype": "Downtime Entry",
					"naming_series": "DT-",
					"workstation": workstation,
					"operator": operator,
					"from_time": from_time,
					"to_time": to_time,
					"stop_reason": "Machine malfunction",
					"remarks": f"Capacity pipeline demo downtime ({mins} mins)",
				}
			)
			doc.insert(ignore_permissions=True)
			created += 1

	return created


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve_company():
	company = (
		frappe.db.get_single_value("Global Defaults", "default_company")
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_value("Company", {}, "name")
	)
	if not company:
		frappe.throw("No Company found on site. Complete ERPNext Setup Wizard first.")
	return company


def _ensure_app_setup():
	from fitzgerald_kitchens.setup.install import after_install

	after_install()


def _set_delivery_planned_date(unit_name, planned_date):
	frappe.db.sql(
		"""
		UPDATE `tabDevelopment Unit Stage`
		SET planned_date = %s, status = 'Ongoing'
		WHERE parent = %s AND stage = %s
		""",
		(getdate(planned_date), unit_name, DELIVERY_STAGE),
	)


def _expected_demo_demand_by_month(from_date, to_date):
	"""Count delivery dates per project/month from DEMO_DELIVERY_SCHEDULE."""
	from_date = getdate(from_date)
	to_date = getdate(to_date)
	by_project = {}
	by_month = {}

	for project, dates in DEMO_DELIVERY_SCHEDULE.items():
		by_project[project] = {}
		for planned_date in dates:
			d = getdate(planned_date)
			if d < from_date or d > to_date:
				continue
			mkey = f"m_{d.year}_{d.month:02d}"
			by_project[project][mkey] = by_project[project].get(mkey, 0) + 1
			by_month[mkey] = by_month.get(mkey, 0) + 1

	return by_project, by_month


def verify_travel_com_capacity_pipeline():
	"""
	Verify Capacity Pipeline calculations on travel.com against DEMO_DELIVERY_SCHEDULE.

	Checks summary rows (capacity, demand, utilisation, free capacity), per-project
	demand, pipeline KPI, and internal row consistency (free = actual − demand).
	"""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		execute,
		get_pipeline_totals,
	)

	if _detect_profile() != "demo":
		frappe.throw("verify_travel_com_capacity_pipeline is for travel.com demo data only.")

	company = DEMO_COMPANY
	filters = frappe._dict(
		{"company": company, "bom": DEMO_KITCHEN_BOM, **KITCHEN_LOCAL_EXPECTED["filters"]}
	)
	from_date = filters["from_date"]
	to_date = filters["to_date"]
	month_keys = ["m_2026_06", "m_2026_07", "m_2026_08"]
	month_labels = {"m_2026_06": "Jun '26", "m_2026_07": "Jul '26", "m_2026_08": "Aug '26"}

	expected_by_project, expected_by_month = _expected_demo_demand_by_month(from_date, to_date)
	_cols, data = execute(filters)

	cap = next((r for r in data if r.get("row_type") == "capacity"), {})
	dem = next((r for r in data if r.get("row_type") == "demand"), {})
	free = next((r for r in data if r.get("row_type") == "free"), {})
	downtime = next((r for r in data if r.get("row_type") == "downtime"), {})
	project_rows = {r["project_id"]: r for r in data if r.get("row_type") == "project"}

	checks = []

	for mkey in month_keys:
		exp_demand = expected_by_month.get(mkey, 0)
		act_demand = int(dem.get(mkey) or 0)
		act_actual = int(cap.get(f"{mkey}_actual") or 0)
		act_theoretical = int(cap.get(f"{mkey}_theoretical") or 0)
		act_free = int(free.get(mkey) or 0)
		act_pct = int(dem.get(f"{mkey}_pct") or 0)
		exp_pct = int(act_demand / act_actual * 100) if act_actual else 0
		exp_free = act_actual - act_demand

		for field, expected, actual in (
			("demand", exp_demand, act_demand),
			("free_capacity", exp_free, act_free),
			("utilisation_pct", exp_pct, act_pct),
		):
			checks.append(
				{
					"scope": "summary",
					"month": month_labels[mkey],
					"field": field,
					"expected": expected,
					"actual": actual,
					"ok": expected == actual,
				}
			)

		checks.append(
			{
				"scope": "summary",
				"month": month_labels[mkey],
				"field": "capacity_actual_lte_theoretical",
				"expected": True,
				"actual": act_actual <= act_theoretical,
				"ok": act_actual <= act_theoretical,
			}
		)
		checks.append(
			{
				"scope": "summary",
				"month": month_labels[mkey],
				"field": "downtime_mins",
				"expected": ">= 0",
				"actual": int(downtime.get(mkey) or 0),
				"ok": int(downtime.get(mkey) or 0) >= 0,
			}
		)

	for mkey in month_keys:
		proj_sum = sum(int(row.get(mkey) or 0) for row in project_rows.values())
		dem_total = int(dem.get(mkey) or 0)
		checks.append(
			{
				"scope": "consistency",
				"month": month_labels[mkey],
				"field": "project_rows_sum_equals_demand",
				"expected": dem_total,
				"actual": proj_sum,
				"ok": proj_sum == dem_total,
			}
		)

	for project_id, exp_months in expected_by_project.items():
		row = project_rows.get(project_id)
		if not row:
			checks.append(
				{
					"scope": "project",
					"project": project_id,
					"field": "in_report",
					"expected": True,
					"actual": False,
					"ok": False,
				}
			)
			continue

		for mkey in month_keys:
			exp = exp_months.get(mkey, 0)
			act = int(row.get(mkey) or 0)
			checks.append(
				{
					"scope": "project",
					"project": project_id,
					"month": month_labels[mkey],
					"field": "demand",
					"expected": exp,
					"actual": act,
					"ok": exp == act,
				}
			)

	pipeline = get_pipeline_totals(filters)
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		_count_pipeline_kitchen_unit_projects,
		_count_pipeline_kitchen_units,
		_projects_for_demand_total,
		_q_projects,
	)

	all_filters = frappe._dict({**filters, "bom": None})
	projects = _q_projects(all_filters)
	demand_projects = _projects_for_demand_total(projects)
	project_names = [p.name for p in demand_projects]
	exp_total = _count_pipeline_kitchen_units(project_names)
	exp_projects = _count_pipeline_kitchen_unit_projects(project_names)
	for field, expected, actual in (
		("total_demand", exp_total, pipeline.get("total_demand")),
		("total_kitchens", exp_total, pipeline.get("total_kitchens")),
		("project_count", exp_projects, pipeline.get("project_count")),
	):
		checks.append(
			{
				"scope": "pipeline_kpi",
				"field": field,
				"expected": expected,
				"actual": actual,
				"ok": expected == actual,
			}
		)

	failed = [c for c in checks if not c.get("ok")]
	return {
		"all_passed": not failed,
		"failed_count": len(failed),
		"failed": failed[:20],
		"checks_passed": len(checks) - len(failed),
		"checks_total": len(checks),
		"expected_monthly_demand": {
			month_labels[k]: expected_by_month.get(k, 0) for k in month_keys
		},
		"actual_summary": {
			month_labels[k]: {
				"capacity": cap.get(k),
				"demand": int(dem.get(k) or 0),
				"free_capacity": int(free.get(k) or 0),
				"utilisation_pct": int(dem.get(f"{k}_pct") or 0),
				"downtime_mins": int(downtime.get(k) or 0),
			}
			for k in month_keys
		},
		"pipeline_kpi": pipeline,
	}


def audit_travel_com_capacity_pipeline():
	"""
	Diagnose Capacity Pipeline data issues on travel.com (demo profile).

	Run after fixes or when report numbers look wrong.
	"""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		_project_kitchen_bom,
		execute,
		get_default_bom,
		get_pipeline_totals,
	)

	if _detect_profile() != "demo":
		frappe.throw("audit_travel_com_capacity_pipeline is for travel.com demo data only.")

	company = DEMO_COMPANY
	filters = frappe._dict({"company": company, **KITCHEN_LOCAL_EXPECTED["filters"]})
	default_bom = get_default_bom(company)
	demo_bom = DEMO_KITCHEN_BOM

	project_stats = frappe.db.sql(
		"""
		SELECT
			COUNT(*) AS active_projects,
			SUM(fk_effective_bom IS NOT NULL) AS with_fk_bom,
			SUM(kitchen_bom IS NOT NULL) AS with_kitchen_bom
		FROM `tabProject`
		WHERE
			company = %(company)s
			AND docstatus < 2
			AND status NOT IN ('Cancelled', 'Completed')
		""",
		{"company": company},
		as_dict=True,
	)[0]

	demo_projects = []
	for project_id in DEMO_DELIVERY_SCHEDULE:
		if not frappe.db.exists("Project", project_id):
			continue
		proj = frappe.get_doc("Project", project_id)
		unit_count = frappe.db.count("Development Unit", {"project": project_id})
		demo_projects.append(
			{
				"project": project_id,
				"project_name": proj.project_name,
				"fk_effective_bom": proj.get("fk_effective_bom"),
				"kitchen_bom": proj.get("kitchen_bom"),
				"effective_bom": _project_kitchen_bom(proj),
				"development_units": unit_count,
				"scheduled_units": len(DEMO_DELIVERY_SCHEDULE[project_id]),
			}
		)

	report_filters = frappe._dict({**filters, "bom": demo_bom})
	_cols, data = execute(report_filters)
	cap = next((r for r in data if r.get("row_type") == "capacity"), {})
	dem = next((r for r in data if r.get("row_type") == "demand"), {})
	project_rows = [r for r in data if r.get("row_type") == "project"]

	issues = []
	if default_bom != demo_bom:
		issues.append(
			f"Default BOM is {default_bom!r} but demo data uses {demo_bom!r} — "
			"select the demo BOM or re-run insert_capacity_pipeline_test_data."
		)
	for row in demo_projects:
		if row["development_units"] < row["scheduled_units"]:
			issues.append(
				f"{row['project']} has {row['development_units']} units but "
				f"schedule expects {row['scheduled_units']} — re-run demo seed."
			)
		if not row["effective_bom"]:
			issues.append(f"{row['project']} has no effective BOM assigned.")

	return {
		"company": company,
		"default_bom": default_bom,
		"demo_bom": demo_bom,
		"default_matches_demo": default_bom == demo_bom,
		"project_stats": project_stats,
		"demo_projects": demo_projects,
		"report_project_count": len(project_rows),
		"report_projects": [r.get("project") for r in project_rows],
		"summary_jun_26": {
			"capacity": cap.get("m_2026_06"),
			"demand": dem.get("m_2026_06"),
			"utilisation_pct": dem.get("m_2026_06_pct"),
		},
		"pipeline_kpi": get_pipeline_totals(filters),
		"issues": issues,
		"healthy": not issues,
	}
