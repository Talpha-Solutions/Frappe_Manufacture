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

KITCHEN_LOCAL_EXPECTED = {
	"filters": {
		"from_date": "2026-06-01",
		"to_date": "2026-08-31",
	},
	"pipeline_kpi": {
		"total_demand": 12,
		"project_count": 5,
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
	"""Verify Total kitchens in pipeline KPI (stable when BOM changes)."""
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
			checks.append(
				{
					"filter": label,
					"field": field,
					"expected": exp,
					"actual": totals.get(field),
					"ok": totals.get(field) == exp,
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
	- Raw Development Unit delivery counts in the report horizon
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
	"""Return (units, kitchens, robes) parsed from a Site subtitle string."""
	units = kitchens = robes = 0
	if not subtitle:
		return units, kitchens, robes
	match = re.search(r"(\d+)\s+units", subtitle or "")
	if match:
		units = int(match.group(1))
	match = re.search(r"(\d+)\s+kitchens", subtitle or "")
	if match:
		kitchens = int(match.group(1))
	match = re.search(r"(\d+)\s+robes", subtitle or "")
	if match:
		robes = int(match.group(1))
	return units, kitchens, robes


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
			sub_units == sum_demand
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
	"""Delivery-stage Development Unit counts per project (report horizon)."""
	rows = frappe.db.sql(
		"""
		SELECT
			p.project_name,
			p.project_type,
		 DATE_FORMAT(dus.planned_date, '%%Y-%%m') AS ym,
		 COUNT(*) AS units,
		 SUM(CASE WHEN IFNULL(p.kitchen_required, 0) = 1
			 OR p.project_type = 'Kitchen' THEN 1 ELSE 0 END) AS kitchens,
		 SUM(CASE WHEN IFNULL(p.wardrobe_required, 0) = 1
			 OR p.project_type = 'Robe' THEN 1 ELSE 0 END) AS robes
		FROM
			`tabDevelopment Unit` du
			INNER JOIN `tabDevelopment Unit Stage` dus ON dus.parent = du.name
			INNER JOIN `tabDevelopment Stage` ds ON ds.name = dus.stage
			INNER JOIN `tabProject` p ON p.name = du.project
		WHERE
			ds.stage_category = 'Delivery'
			AND dus.planned_date BETWEEN %(from_date)s AND %(to_date)s
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
			project_name, bom_map[bom_key], refs["customer"], company
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
):
	existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
	values = {
		"kitchen_required": 1,
		"kitchen_bom": kitchen_bom,
		"kitchen_item": frappe.db.get_value("BOM", kitchen_bom, "item"),
		"customer": customer,
		"company": company,
		"expected_start_date": KITCHEN_LOCAL_PROJECT_START_DATE,
	}
	if project_type:
		values["project_type"] = project_type
	if site_parent is not None:
		values["fk_parent_project"] = site_parent

	if existing:
		update_values = {
			"fk_effective_bom": kitchen_bom,
			"project_type": "Kitchen",
			"customer": customer,
			"company": company,
		}
		if site_parent is not None:
			update_values["fk_parent_project"] = site_parent
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
			"project_type": "Kitchen",
			"status": "Open",
			"expected_start_date": KITCHEN_LOCAL_PROJECT_START_DATE,
			**({"project_type": project_type} if project_type else {}),
			**({"fk_parent_project": site_parent} if site_parent else {}),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


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
	for project in DEMO_DELIVERY_SCHEDULE:
		if not frappe.db.exists("Project", project):
			continue

		frappe.db.set_value(
			"Project",
			project,
			{
				"fk_effective_bom": DEMO_KITCHEN_BOM,
				"project_type": "Kitchen",
			},
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
