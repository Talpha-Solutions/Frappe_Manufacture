# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Insert sample data for validating the Capacity Pipeline Report."""

import frappe
from frappe.utils import add_to_date, getdate, now_datetime


COMPANY = "Fitzgerald Kitchens (Demo)"
KITCHEN_BOM = "BOM-BOM-KIT-TYPE-A-SOCIAL-001-001"
ROUTING = "Cabinet Manufacturing - Standard"
DELIVERY_STAGE = "Kitchen Delivered"

# Sample downtime on bottleneck workstation (Edge Bander) — month -> total mins
DOWNTIME_BY_MONTH = {
	"2026-06": [200, 800],
	"2026-07": [300],
	"2026-08": [1500],
}

# project -> list of delivery planned dates (YYYY-MM-DD)
DELIVERY_SCHEDULE = {
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


def insert_capacity_pipeline_test_data():
	"""Populate demo site with delivery dates and BOM routing for report testing."""
	_enable_bom_capacity()
	_set_project_kitchen_boms()
	updated = _update_existing_delivery_dates()
	created = _create_development_units()
	downtime_created = _create_downtime_entries()
	frappe.db.commit()

	return {
		"bom_updated": KITCHEN_BOM,
		"projects_updated": len(DELIVERY_SCHEDULE),
		"delivery_dates_updated": updated,
		"development_units_created": created,
		"downtime_entries_created": downtime_created,
	}


def _enable_bom_capacity():
	if not frappe.db.exists("BOM", KITCHEN_BOM):
		frappe.throw(f"BOM {KITCHEN_BOM} not found")

	frappe.db.set_value(
		"BOM",
		KITCHEN_BOM,
		{
			"routing": ROUTING,
			"with_operations": 1,
		},
		update_modified=True,
	)


def _set_project_kitchen_boms():
	for project in DELIVERY_SCHEDULE:
		if not frappe.db.exists("Project", project):
			continue

		frappe.db.set_value(
			"Project",
			project,
			{
				"kitchen_required": 1,
				"kitchen_bom": KITCHEN_BOM,
				"kitchen_item": frappe.db.get_value("BOM", KITCHEN_BOM, "item"),
			},
			update_modified=False,
		)


def _update_existing_delivery_dates():
	count = 0
	for project, dates in DELIVERY_SCHEDULE.items():
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


def _create_development_units():
	created = 0
	for project, dates in DELIVERY_SCHEDULE.items():
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
					"company": COMPANY,
					"customer": _get_project_customer(project),
					"kitchen_required": 1,
					"kitchen_bom": KITCHEN_BOM,
				}
			)
			doc.insert(ignore_permissions=True)
			_set_delivery_planned_date(doc.name, planned_date)
			created += 1

	return created


def _set_delivery_planned_date(unit_name, planned_date):
	frappe.db.sql(
		"""
		UPDATE `tabDevelopment Unit Stage`
		SET planned_date = %s, status = 'Ongoing'
		WHERE parent = %s AND stage = %s
		""",
		(getdate(planned_date), unit_name, DELIVERY_STAGE),
	)


def _get_project_customer(project):
	customer = frappe.db.get_value("Project", project, "customer")
	if customer:
		return customer

	return frappe.db.get_value("Customer", {"disabled": 0}, "name") or "Grant Plastics Ltd."


def _create_downtime_entries():
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
	for ym, durations in DOWNTIME_BY_MONTH.items():
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
