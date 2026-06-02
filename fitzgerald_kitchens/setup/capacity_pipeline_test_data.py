# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Test data for validating the Capacity Pipeline Report.

Two profiles:

* **kitchen_local** — self-contained small numbers (2 BOMs, capacity 10 & 20,
  3 projects, 8 delivery units, June downtime). Use on fresh sites like
  ``kitchen.local``.
* **demo** — overlays delivery dates / units / downtime onto an existing
  Fitzgerald demo site (``travel.com``).

Run::

    bench --site kitchen.local execute fitzgerald_kitchens.setup.capacity_pipeline_test_data.insert_capacity_pipeline_test_data
    bench --site kitchen.local execute fitzgerald_kitchens.setup.capacity_pipeline_test_data.verify_capacity_pipeline_test_data
"""

import calendar
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

KITCHEN_LOCAL_EXPECTED = {
	"filters": {
		"from_date": "2026-06-01",
		"to_date": "2026-08-31",
	},
	"BOM-A (capacity 10)": {
		"bom_item": "Kitchen Type A - KT",
		"projects": ["Alpha Kitchens", "Beta Kitchens"],
		"months": {
			"Jun '26": {"capacity": "9/10", "demand": 3, "utilisation_pct": 33, "free_capacity": 6},
			"Jul '26": {"capacity": "10/10", "demand": 2, "utilisation_pct": 20, "free_capacity": 8},
			"Aug '26": {"capacity": "10/10", "demand": 0, "utilisation_pct": 0, "free_capacity": 10},
		},
	},
	"BOM-B (capacity 20)": {
		"bom_item": "Kitchen Type B - KT",
		"projects": ["Gamma Kitchens"],
		"months": {
			"Jun '26": {"capacity": "18/20", "demand": 0, "utilisation_pct": 0, "free_capacity": 18},
			"Jul '26": {"capacity": "20/20", "demand": 1, "utilisation_pct": 5, "free_capacity": 19},
			"Aug '26": {"capacity": "20/20", "demand": 2, "utilisation_pct": 10, "free_capacity": 18},
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

	_ensure_app_setup()
	refs = _create_kitchen_local_masters(company)
	_create_kitchen_local_projects_and_units(refs, company)
	job_cards = _create_kitchen_local_job_cards(refs, company)
	downtime = _create_kitchen_local_downtime(refs["workstation"], company)
	frappe.db.commit()
	return _kitchen_local_summary("seeded", company, downtime=downtime, job_cards=job_cards, **refs)


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
	project_names = list(KITCHEN_LOCAL_PROJECTS.keys())
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


def _get_or_create_kitchen_local_project(project_name, kitchen_bom, customer, company):
	existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
	if existing:
		frappe.db.set_value(
			"Project",
			existing,
			{
				"fk_effective_bom": kitchen_bom,
				"project_type": "Kitchen",
				"customer": customer,
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
			"customer": customer,
			"fk_effective_bom": kitchen_bom,
			"project_type": "Kitchen",
			"status": "Open",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_kitchen_local_downtime(workstation, company):
	if frappe.db.exists("Downtime Entry", {"remarks": MARKER}):
		return 0

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


def _remove_kitchen_local_manufacturing_data():
	project_names = list(KITCHEN_LOCAL_PROJECTS.keys())
	projects = frappe.get_all(
		"Project", filters={"project_name": ["in", project_names]}, pluck="name"
	)
	if not projects:
		return {"job_cards": 0, "work_orders": 0}

	removed_jc = 0
	wo_names = set()
	for name in frappe.get_all(
		"Job Card", filters={"project": ["in", projects], "remarks": MARKER}, pluck="name"
	):
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

	for project_name, (bom_key, dates) in KITCHEN_LOCAL_PROJECTS.items():
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
