# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Demo / test data for Project Tender Profit Margin on travel.com.

Seeds predictable kitchen-unit cost profiles on selected Site projects only.
Tender Price Per Kitchen comes from the linked Tender Configuration (saved/calculated).
Each profile can include manufacturing (Job Cards), task cost (Timesheets), and
project totals for expense / purchase / material.

	Run::

    bench --site travel.com execute fitzgerald_kitchens.setup.tender_profit_margin_test_data.clear_travel_com_tender_profit_margin_test_data
    bench --site travel.com execute fitzgerald_kitchens.setup.tender_profit_margin_test_data.seed_travel_com_tender_profit_margin_test_data
    bench --site travel.com execute fitzgerald_kitchens.setup.tender_profit_margin_test_data.verify_travel_com_tender_profit_margin_test_data
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, flt, getdate, get_datetime, today

from fitzgerald_kitchens.fitzgerald_kitchens.report.project_tender_profit_margin.project_tender_profit_margin import (
	compute_profit_margin_metrics,
	get_data,
)
from fitzgerald_kitchens.setup.capacity_pipeline_test_data import (
	DEMO_COMPANY,
	DEMO_KITCHEN_BOM,
	_enable_demo_bom_capacity,
	_get_demo_warehouse,
	_get_demo_workstation,
)

MARKER = "Tender profit margin test data"
DEMO_BOM_CANDIDATES = (
	"BOM-KIT-1BED-A-SOCIAL-002",
	"BOM-BOM-KIT-TYPE-A-SOCIAL-001-002",
	"BOM-B60-001",
	DEMO_KITCHEN_BOM,
)

# Site → tender link + explicit kitchen unit cost profiles only.
# Tender Price Per Kitchen comes from the linked Tender Configuration (saved/calculated).
# Profiles are sized relative to a typical calculated tender (~£1,848 on travel.com).
DEMO_SITES: dict[str, dict] = {
	"PROJ-0014": {
		"tender_name": "Tender Margin Demo - The Avenue",
		"delayed": True,
		"units": {
			"UNIT-KIT-00001": {
				"note": "Under tender — all five cost segments",
				"total_purchase_cost": 350,
				"total_consumed_material_cost": 280,
				"total_expense_claim": 120,
				"manufacturing_mins": 180,
				"hour_rate": 50,
				"task_actual_cost": 240,
			},
			"UNIT-KIT-00002": {
				"note": "Under tender — material only",
				"total_consumed_material_cost": 520,
			},
			"UNIT-KIT-00003": {
				"note": "Near tender",
				"total_purchase_cost": 520,
				"total_consumed_material_cost": 420,
				"total_expense_claim": 220,
				"manufacturing_mins": 300,
				"hour_rate": 52,
				"task_actual_cost": 320,
			},
			"UNIT-KIT-00004": {
				"note": "Over tender",
				"total_purchase_cost": 780,
				"total_consumed_material_cost": 650,
				"total_expense_claim": 380,
				"manufacturing_mins": 540,
				"hour_rate": 58,
				"task_actual_cost": 480,
			},
		},
	},
	"PROJ-0015": {
		"tender_name": "Tender Margin Demo - The Lane",
		"tender_docname": "KC-DEMO-LANE",
		"delayed": False,
		"units": {
			"UNIT-KIT-00025": {
				"note": "Under tender — purchase, material, expense, task",
				"total_purchase_cost": 300,
				"total_consumed_material_cost": 250,
				"total_expense_claim": 100,
				"task_actual_cost": 180,
			},
			"UNIT-KIT-00026": {
				"note": "Near tender",
				"total_purchase_cost": 480,
				"total_consumed_material_cost": 390,
				"total_expense_claim": 200,
				"manufacturing_mins": 280,
				"hour_rate": 54,
				"task_actual_cost": 340,
			},
			"UNIT-KIT-00027": {
				"note": "Over tender",
				"total_purchase_cost": 720,
				"total_consumed_material_cost": 600,
				"total_expense_claim": 350,
				"manufacturing_mins": 600,
				"hour_rate": 56,
				"task_actual_cost": 420,
			},
		},
	},
}


def clear_travel_com_tender_profit_margin_test_data():
	"""Remove seeded costs, manufacturing, timesheets, and tender links from demo sites."""
	_assert_demo_sites_exist()
	removed = _remove_all_marker_manufacturing()
	timesheets_removed = _remove_marker_timesheets()
	stray_cleared = _clear_stray_activity_on_non_profile_units()
	costs_cleared = _clear_kitchen_costs_for_demo_sites()
	sites_reset = _reset_demo_site_fields()
	frappe.db.commit()

	result = {
		"demo_sites": list(DEMO_SITES),
		"kitchen_costs_cleared": costs_cleared,
		"removed_work_orders": removed.get("work_orders", 0),
		"removed_job_cards": removed.get("job_cards", 0),
		"removed_timesheets": timesheets_removed,
		"stray_units_cleared": stray_cleared,
		"sites_reset": sites_reset,
	}
	print("\n=== Clear tender profit margin test data (travel.com) ===")
	for key, value in result.items():
		print(f"  {key}: {value}")
	print("=== Done ===\n")
	return result


def seed_travel_com_tender_profit_margin_test_data():
	"""Apply targeted tender profit margin demo data on travel.com."""
	_assert_demo_sites_exist()
	clear_travel_com_tender_profit_margin_test_data()

	tenders_linked = {}
	units_profiled = 0
	manufacturing_created = 0
	timesheets_created = 0
	manufacturing_slot = 0

	for site, config in DEMO_SITES.items():
		tender = _ensure_site_tender(site, config)
		_link_site_to_tender(site, tender)
		_configure_demo_site(site, config)
		profiles = config["units"]
		created, manufacturing_slot = _create_unit_manufacturing(site, profiles, manufacturing_slot)
		manufacturing_created += created
		task_created, manufacturing_slot = _create_unit_task_costs(profiles, manufacturing_slot)
		timesheets_created += task_created
		units_profiled += _apply_unit_cost_profiles(site, profiles)
		tenders_linked[site] = tender

	frappe.db.commit()

	print("\n=== Tender profit margin test data (travel.com) ===")
	print(f"  company: {DEMO_COMPANY}")
	print(f"  demo_sites: {list(DEMO_SITES.keys())}")
	print(f"  kitchen_units_profiled: {units_profiled}")
	print(f"  manufacturing_units_created: {manufacturing_created}")
	print(f"  timesheets_created: {timesheets_created}")
	for site, config in DEMO_SITES.items():
		tender_price = _get_linked_tender_price_per_kitchen(site)
		print(f"\n  {site} — {frappe.db.get_value('Project', site, 'project_name')}")
		print(f"    tender: {tenders_linked[site]} @ {tender_price}")
		for unit, profile in config["units"].items():
			metrics = _profile_metrics(profile, tender_price)
			status = "OVER" if metrics["total_cost"] > tender_price else "under"
			print(
				f"    {unit}: total={metrics['total_cost']:.2f} "
				f"(mfg={metrics['manufacturing_actual_cost']:.2f} "
				f"task={metrics['task_actual_cost']:.2f}) "
				f"margin={metrics['profit_margin']:.2f} ({status})"
			)
	print("=== Done ===\n")
	return {
		"sites": list(DEMO_SITES.keys()),
		"kitchen_units_profiled": units_profiled,
		"manufacturing_units_created": manufacturing_created,
		"timesheets_created": timesheets_created,
		"tenders_linked": tenders_linked,
	}


def restore_travel_com_tender_pricing_from_configuration():
	"""Recalculate tender prices from Tender Configuration and sync linked Site projects."""
	_assert_demo_sites_exist()
	updated = []

	for site, config in DEMO_SITES.items():
		tender = frappe.db.get_value("Project", site, "fk_tender_configuration")
		if not tender:
			tender = _ensure_site_tender(site, config)
		else:
			_recalculate_tender_pricing(tender, config)
		_link_site_to_tender(site, tender)
		updated.append(
			{
				"site": site,
				"tender": tender,
				"tender_price_per_kitchen": _get_linked_tender_price_per_kitchen(site),
			}
		)

	frappe.db.commit()
	print("\n=== Restore tender pricing from Tender Configuration (travel.com) ===")
	for row in updated:
		print(
			f"  {row['site']}: {row['tender']} → Tender Price Per Kitchen = {row['tender_price_per_kitchen']}"
		)
	print("=== Done ===\n")
	return {"ok": True, "sites": updated}


def verify_travel_com_tender_profit_margin_test_data():
	"""Verify report rows and calculated values per demo site filter."""
	_assert_demo_sites_exist()
	report_filters = frappe._dict(
		company=DEMO_COMPANY,
		from_date=add_to_date(today(), years=-1),
		to_date=add_to_date(today(), years=1),
	)

	all_ok = True
	site_results = []

	for site, config in DEMO_SITES.items():
		tender = frappe.db.get_value("Project", site, "fk_tender_configuration")
		if not tender:
			frappe.throw(f"Site {site} has no tender link. Run seed first.")

		tender_price = _get_linked_tender_price_per_kitchen(site)
		if not tender_price:
			frappe.throw(f"Site {site}: linked tender {tender} has no Tender Price Per Kitchen.")

		filters = frappe._dict(report_filters)
		filters.site_project = site
		rows = get_data(filters)
		expected_units = set(config["units"])
		found_units = {row["kitchen_unit"] for row in rows}

		missing = expected_units - found_units
		if missing:
			all_ok = False
			site_results.append(
				{
					"site": site,
					"ok": False,
					"error": f"missing units: {', '.join(sorted(missing))}",
				}
			)
			continue

		unit_checks = []
		for unit, profile in config["units"].items():
			row = next(item for item in rows if item["kitchen_unit"] == unit)
			expected = _expected_report_row(profile, tender_price, site)
			check = _compare_report_row(row, expected)
			unit_checks.append({"unit": unit, **check})
			if not check["ok"]:
				all_ok = False

		extra_units = found_units - expected_units
		site_results.append(
			{
				"site": site,
				"site_name": frappe.db.get_value("Project", site, "project_name"),
				"ok": all(check["ok"] for check in unit_checks),
				"row_count": len(rows),
				"expected_units": len(expected_units),
				"extra_units": len(extra_units),
				"units": unit_checks,
				"delayed": any(frappe.utils.cint(r.get("is_site_delayed")) for r in rows),
			}
		)

	print("\n=== Verify tender profit margin (travel.com) ===")
	for result in site_results:
		status = "OK" if result.get("ok") else "FAIL"
		print(f"\n  [{status}] {result['site']} — {result.get('site_name', '')}")
		if result.get("error"):
			print(f"    {result['error']}")
			continue
		print(f"    rows: {result['row_count']} (expected {result.get('expected_units', '')})")
		if result.get("extra_units"):
			print(f"    extra units in report: {result['extra_units']}")
		print(f"    delayed flag: {result.get('delayed')}")
		for unit in result.get("units", []):
			flag = "ok" if unit["ok"] else "MISMATCH"
			print(f"    {unit['unit']}: {flag} total={unit.get('actual_total')} (exp {unit.get('expected_total')})")
			if not unit["ok"]:
				print(f"      diffs: {unit.get('diffs')}")

	if not all_ok:
		frappe.throw("Tender profit margin verification failed. See output above.")

	print("\n=== All demo sites verified ===\n")
	return {"ok": True, "sites": site_results}


def _expected_report_row(profile: dict, tender_price: float, site: str) -> dict:
	metrics = _profile_metrics(profile, tender_price)
	return {
		"site": site,
		"manufacturing_actual_cost": metrics["manufacturing_actual_cost"],
		"task_actual_cost": metrics["task_actual_cost"],
		"total_expense_claim": metrics["total_expense_claim"],
		"total_purchase_cost": metrics["total_purchase_cost"],
		"total_consumed_material_cost": metrics["total_consumed_material_cost"],
		"total_cost": metrics["total_cost"],
		"tender_price_per_kitchen": tender_price,
		"profit_margin": metrics["profit_margin"],
		"cost_variance": metrics["cost_variance"],
		"margin_pct": metrics["margin_pct"],
	}


def _compare_report_row(actual: dict, expected: dict) -> dict:
	fields = (
		"manufacturing_actual_cost",
		"task_actual_cost",
		"total_expense_claim",
		"total_purchase_cost",
		"total_consumed_material_cost",
		"total_cost",
		"tender_price_per_kitchen",
		"profit_margin",
		"cost_variance",
		"margin_pct",
	)
	diffs = {}
	for field in fields:
		act = flt(actual.get(field), 2)
		exp = flt(expected.get(field), 2)
		if abs(act - exp) > 0.05:
			diffs[field] = {"actual": act, "expected": exp}

	return {
		"ok": not diffs,
		"actual_total": flt(actual.get("total_cost"), 2),
		"expected_total": flt(expected.get("total_cost"), 2),
		"diffs": diffs,
	}


def _assert_demo_sites_exist():
	for site in DEMO_SITES:
		if not frappe.db.exists("Project", site):
			frappe.throw(f"Demo site project {site} not found on this site.")
		if frappe.db.get_value("Project", site, "project_type") != "Site":
			frappe.throw(f"{site} must be a Site project.")


def _get_kitchen_units_for_site(site: str) -> list[str]:
	return frappe.get_all(
		"Project",
		filters={
			"fk_parent_project": site,
			"project_type": "Kitchen",
			"docstatus": ("<", 2),
		},
		pluck="name",
		order_by="name asc",
	)


def _profile_metrics(profile: dict, tender_price: float) -> dict:
	mfg = (flt(profile.get("manufacturing_mins")) / 60) * flt(profile.get("hour_rate"))
	task = flt(profile.get("task_actual_cost"))
	return compute_profit_margin_metrics(
		mfg,
		profile.get("total_expense_claim"),
		profile.get("total_purchase_cost"),
		profile.get("total_consumed_material_cost"),
		tender_price,
		task_actual_cost=task,
	)


def _ensure_site_tender(site: str, config: dict) -> str:
	tender_name = config["tender_name"]
	explicit_name = config.get("tender_docname")
	kitchens = len(config["units"])

	tender = frappe.db.get_value("Tender Configuration", {"tender_name": tender_name}, "name")
	if not tender and explicit_name and frappe.db.exists("Tender Configuration", explicit_name):
		tender = explicit_name
	elif not tender and explicit_name:
		tender = _create_tender_with_name(explicit_name, tender_name, kitchens)
	elif not tender:
		tender = _create_tender_from_reference(tender_name, kitchens)

	_recalculate_tender_pricing(tender, config)
	return tender


def _recalculate_tender_pricing(tender: str, config: dict) -> None:
	"""Save tender so validate() recalculates Tender Price Per Kitchen from costing."""
	doc = frappe.get_doc("Tender Configuration", tender)
	doc.tender_name = config["tender_name"]
	doc.kitchens_to_tender = len(config["units"])
	doc.save(ignore_permissions=True)


def _get_linked_tender_price_per_kitchen(site: str) -> float:
	tender = frappe.db.get_value("Project", site, "fk_tender_configuration")
	if not tender:
		return 0
	return flt(frappe.db.get_value("Tender Configuration", tender, "tender_price_per_kitchen"))


def _create_tender_with_name(name: str, tender_name: str, kitchens: int) -> str:
	reference = frappe.get_all("Tender Configuration", pluck="name", limit=1)
	if not reference:
		frappe.throw("No Tender Configuration found to use as reference.")

	ref_doc = frappe.get_doc("Tender Configuration", reference[0])
	doc = frappe.new_doc("Tender Configuration")
	doc.update(
		{
			"template": ref_doc.template,
			"tender_name": tender_name,
			"kitchens_to_tender": kitchens,
			"target_margin_pct": ref_doc.target_margin_pct,
			"base_units": ref_doc.base_units,
			"wall_units": ref_doc.wall_units,
			"tall_units": ref_doc.tall_units,
			"drawer_packs": ref_doc.drawer_packs,
			"config_rows_json": ref_doc.config_rows_json,
			"cabinet_prices_json": ref_doc.cabinet_prices_json,
		}
	)
	doc.insert(ignore_permissions=True, set_name=name)
	return doc.name


def _create_tender_from_reference(tender_name: str, kitchens: int) -> str:
	reference = frappe.get_all("Tender Configuration", pluck="name", limit=1)
	if not reference:
		frappe.throw("No Tender Configuration found to use as reference.")

	ref_doc = frappe.get_doc("Tender Configuration", reference[0])
	doc = frappe.new_doc("Tender Configuration")
	doc.update(
		{
			"template": ref_doc.template,
			"tender_name": tender_name,
			"kitchens_to_tender": kitchens,
			"target_margin_pct": ref_doc.target_margin_pct,
			"base_units": ref_doc.base_units,
			"wall_units": ref_doc.wall_units,
			"tall_units": ref_doc.tall_units,
			"drawer_packs": ref_doc.drawer_packs,
			"config_rows_json": ref_doc.config_rows_json,
			"cabinet_prices_json": ref_doc.cabinet_prices_json,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _link_site_to_tender(site: str, tender: str) -> None:
	tender_price = flt(
		frappe.db.get_value("Tender Configuration", tender, "tender_price_per_kitchen")
	)
	frappe.db.set_value(
		"Project",
		site,
		{
			"fk_tender_configuration": tender,
			"fk_tender_price_per_kitchen": tender_price,
		},
		update_modified=True,
	)


def _configure_demo_site(site: str, config: dict) -> None:
	values = {"status": "Open"}
	if config.get("delayed"):
		values["expected_end_date"] = add_to_date(today(), days=-21)
	else:
		values["expected_end_date"] = add_to_date(today(), days=60)
	frappe.db.set_value("Project", site, values, update_modified=True)


def _reset_demo_site_fields() -> int:
	reset = 0
	for site in DEMO_SITES:
		frappe.db.set_value(
			"Project",
			site,
			{
				"fk_tender_configuration": None,
				"fk_tender_price_per_kitchen": 0,
				"expected_end_date": None,
			},
			update_modified=True,
		)
		reset += 1
	return reset


def _clear_kitchen_costs_for_demo_sites() -> int:
	cleared = 0
	for site in DEMO_SITES:
		for unit in _get_kitchen_units_for_site(site):
			frappe.db.set_value(
				"Project",
				unit,
				{
					"total_purchase_cost": 0,
					"total_consumed_material_cost": 0,
					"total_expense_claim": 0,
				},
				update_modified=False,
			)
			cleared += 1
	return cleared


def _apply_unit_cost_profiles(site: str, profiles: dict[str, dict]) -> int:
	updated = 0
	for unit, profile in profiles.items():
		if not frappe.db.exists("Project", unit):
			frappe.throw(f"Kitchen unit {unit} not found.")
		if frappe.db.get_value("Project", unit, "fk_parent_project") != site:
			frappe.throw(f"Kitchen unit {unit} is not under site {site}.")

		values = {
			key: flt(value)
			for key, value in profile.items()
			if key
			in (
				"total_purchase_cost",
				"total_consumed_material_cost",
				"total_expense_claim",
			)
		}
		frappe.db.set_value("Project", unit, values, update_modified=False)
		updated += 1
	return updated


def _remove_all_marker_manufacturing() -> dict:
	removed_jc = 0
	wo_names: set[str] = set()

	for name in frappe.get_all(
		"Job Card",
		filters={"remarks": MARKER},
		pluck="name",
	):
		work_order = frappe.db.get_value("Job Card", name, "work_order")
		if work_order:
			wo_names.add(work_order)
		doc = frappe.get_doc("Job Card", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Job Card", name, ignore_permissions=True, force=True)
		removed_jc += 1

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


def _remove_marker_timesheets() -> int:
	removed = 0
	for name in frappe.get_all("Timesheet", filters={"note": MARKER}, pluck="name"):
		doc = frappe.get_doc("Timesheet", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Timesheet", name, ignore_permissions=True, force=True)
		removed += 1
	return removed


def _clear_stray_activity_on_non_profile_units() -> int:
	"""Cancel submitted timesheets / work orders on non-profile kitchen units under demo sites."""
	cleared = 0
	for site, config in DEMO_SITES.items():
		profile_units = set(config["units"])
		for unit in _get_kitchen_units_for_site(site):
			if unit in profile_units:
				continue
			cleared += _cancel_timesheets_for_project(unit)
			cleared += _cancel_work_orders_for_project(unit)
	return cleared


def _cancel_timesheets_for_project(project: str) -> int:
	cancelled = 0
	for name in frappe.db.sql(
		"""
		select distinct ts.name
		from `tabTimesheet` ts
		inner join `tabTimesheet Detail` td on td.parent = ts.name
		where ts.docstatus = 1 and td.project = %s
		""",
		project,
	):
		doc = frappe.get_doc("Timesheet", name[0])
		doc.cancel()
		cancelled += 1
	return cancelled


def _cancel_work_orders_for_project(project: str) -> int:
	cancelled = 0
	for name in frappe.get_all(
		"Work Order",
		filters={"project": project, "docstatus": 1},
		pluck="name",
	):
		doc = frappe.get_doc("Work Order", name)
		doc.cancel()
		cancelled += 1
	return cancelled


def _create_unit_task_costs(profiles: dict[str, dict], slot_offset: int = 0) -> tuple[int, int]:
	employee = _get_demo_employee()
	activity_type = _get_demo_activity_type()
	created = 0

	for unit, profile in profiles.items():
		task_cost = flt(profile.get("task_actual_cost") or 0)
		if not task_cost:
			continue

		task = _get_or_create_unit_task(unit)
		hours = max(round(task_cost / 50, 2), 0.5)
		planned_date = add_to_date(today(), days=-(8 + slot_offset * 2))
		from_time = get_datetime(f"{planned_date} 09:00:00")
		to_time = add_to_date(from_time, hours=hours)
		slot_offset += 1

		ts = frappe.new_doc("Timesheet")
		ts.employee = employee
		ts.company = DEMO_COMPANY
		ts.note = MARKER
		ts.append(
			"time_logs",
			{
				"activity_type": activity_type,
				"from_time": from_time,
				"to_time": to_time,
				"hours": hours,
				"project": unit,
				"task": task,
				"costing_hours": hours,
				"costing_rate": flt(task_cost / hours, 2),
				"costing_amount": task_cost,
				"base_costing_amount": task_cost,
			},
		)
		ts.insert(ignore_permissions=True)
		ts.submit()
		created += 1

	return created, slot_offset


def _get_demo_employee() -> str:
	employee = frappe.db.get_value("Employee", {"status": "Active", "company": DEMO_COMPANY}, "name")
	if not employee:
		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if not employee:
		frappe.throw(f"No active Employee found for {DEMO_COMPANY}.")
	return employee


def _get_demo_activity_type() -> str:
	activity_type = frappe.db.get_value("Activity Type", {}, "name")
	if not activity_type:
		frappe.throw("No Activity Type found for timesheet test data.")
	return activity_type


def _get_or_create_unit_task(unit: str) -> str:
	existing = frappe.get_all(
		"Task",
		filters={"project": unit},
		pluck="name",
		order_by="creation asc",
		limit=1,
	)
	if existing:
		return existing[0]

	doc = frappe.new_doc("Task")
	doc.subject = f"{MARKER} — {unit}"
	doc.project = unit
	doc.status = "Open"
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_unit_manufacturing(site: str, profiles: dict[str, dict], slot_offset: int = 0) -> tuple[int, int]:
	bom = _get_active_demo_bom()
	if not bom:
		frappe.throw("No active BOM with operations found for manufacturing test data.")

	if bom == DEMO_KITCHEN_BOM:
		_enable_demo_bom_capacity()

	bottleneck = _get_bottleneck_for_bom(bom)
	if not bottleneck:
		frappe.throw(f"Could not resolve bottleneck operation for BOM {bom}.")

	warehouse = _get_demo_warehouse()
	production_item = frappe.db.get_value("BOM", bom, "item")
	created = 0

	for unit, profile in profiles.items():
		mins = int(profile.get("manufacturing_mins") or 0)
		if not mins:
			continue

		hour_rate = flt(profile.get("hour_rate") or getattr(bottleneck, "hour_rate", None) or 50)
		planned_date = add_to_date(today(), days=-(10 + slot_offset * 2))
		from_time = add_to_date(get_datetime(f"{planned_date} 08:00:00"), hours=slot_offset * 4)
		workstation = _get_or_create_test_workstation(slot_offset, hour_rate)
		slot_offset += 1

		wo = frappe.new_doc("Work Order")
		wo.production_item = production_item
		wo.bom_no = bom
		wo.qty = 1
		wo.company = DEMO_COMPANY
		wo.project = unit
		wo.fg_warehouse = warehouse
		wo.wip_warehouse = warehouse
		wo.skip_transfer = 1
		wo.planned_start_date = getdate(from_time)
		wo.get_items_and_operations_from_bom()
		wo.insert(ignore_permissions=True)

		jc = frappe.new_doc("Job Card")
		jc.work_order = wo.name
		jc.company = DEMO_COMPANY
		jc.project = unit
		jc.bom_no = bom
		jc.production_item = production_item
		jc.operation = bottleneck.operation
		jc.workstation = workstation
		if getattr(bottleneck, "workstation_type", None):
			jc.workstation_type = bottleneck.workstation_type
		jc.for_quantity = 1
		jc.wip_warehouse = warehouse
		jc.hour_rate = hour_rate
		jc.posting_date = getdate(from_time)
		jc.remarks = MARKER

		to_time = add_to_date(from_time, minutes=mins)
		jc.append(
			"time_logs",
			{
				"from_time": from_time,
				"to_time": to_time,
				"time_in_mins": mins,
				"completed_qty": 1,
			},
		)
		jc.insert(ignore_permissions=True)
		jc.submit()
		created += 1

	return created, slot_offset


def _get_active_demo_bom() -> str | None:
	for name in DEMO_BOM_CANDIDATES:
		if not frappe.db.exists("BOM", name):
			continue
		if frappe.db.get_value("BOM", name, "docstatus") != 1:
			continue
		return name
	return frappe.db.get_value(
		"BOM",
		{"docstatus": 1, "is_active": 1, "with_operations": 1},
		"name",
	)


def _get_bottleneck_for_bom(bom: str):
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		_get_bottleneck_operation,
		_q_bom_operations,
	)

	return _get_bottleneck_operation(_q_bom_operations([bom]))


def _get_or_create_test_workstation(slot: int, hour_rate: float) -> str:
	name = f"Tender Margin Test {slot:02d}"
	if frappe.db.exists("Workstation", name):
		frappe.db.set_value("Workstation", name, "hour_rate", hour_rate, update_modified=False)
		return name

	doc = frappe.new_doc("Workstation")
	doc.workstation_name = name
	doc.hour_rate = hour_rate
	doc.workstation_type = frappe.db.get_value("Workstation Type", {}, "name")
	doc.insert(ignore_permissions=True)
	return doc.name
