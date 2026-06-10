# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from fitzgerald_kitchens.fitzgerald_kitchens.report.project_tender_profit_margin.project_tender_profit_margin import (
	compute_profit_margin_metrics,
	get_data,
	_format_site_project_label,
	_get_kitchen_completion_by_site,
	_is_project_delayed,
)
from fitzgerald_kitchens.fitzgerald_kitchens.utils.project_manufacturing_cost import (
	filter_work_orders_by_date,
	get_manufacturing_actual_cost_by_project,
)
from fitzgerald_kitchens.setup.project_naming import get_naming_series_for_project_type
from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields


class TestProjectTenderProfitMargin(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_project_unit_fields()

	def tearDown(self):
		frappe.db.rollback()

	def test_compute_profit_margin_metrics_sums_components(self):
		result = compute_profit_margin_metrics(100, 50, 75, 25, 300)

		self.assertEqual(result["total_cost"], 250)
		self.assertEqual(result["task_actual_cost"], 0)
		self.assertEqual(result["profit_margin"], 50)
		self.assertEqual(result["cost_variance"], -50)
		self.assertAlmostEqual(result["margin_pct"], 16.67, places=2)

	def test_compute_profit_margin_metrics_includes_task_cost(self):
		result = compute_profit_margin_metrics(100, 50, 75, 25, 300, task_actual_cost=40)

		self.assertEqual(result["task_actual_cost"], 40)
		self.assertEqual(result["total_cost"], 290)
		self.assertEqual(result["profit_margin"], 10)

	def test_format_site_project_label(self):
		self.assertEqual(
			_format_site_project_label("PROJ-0014", "The Avenue MOCKSITE"),
			"The Avenue MOCKSITE (PROJ-0014)",
		)
		self.assertEqual(_format_site_project_label("PROJ-0014", ""), "PROJ-0014")

	def test_compute_profit_margin_metrics_over_tender(self):
		result = compute_profit_margin_metrics(200, 100, 100, 100, 300)

		self.assertEqual(result["total_cost"], 500)
		self.assertEqual(result["profit_margin"], -200)
		self.assertEqual(result["cost_variance"], 200)

	def test_is_project_delayed_past_expected_end_date(self):
		row = frappe._dict(status="Open", expected_end_date=add_days(today(), -5))
		self.assertTrue(_is_project_delayed(row))

	def test_is_project_delayed_completed_not_delayed(self):
		row = frappe._dict(status="Completed", expected_end_date=add_days(today(), -5))
		self.assertFalse(_is_project_delayed(row))

	def test_kitchen_excluded_when_site_has_no_tender(self):
		company = self._get_company()
		site = self._create_site("No Tender Site", company=company)
		kitchen = self._create_kitchen("Kitchen A", site.name, company=company)

		data = get_data(self._report_filters(company, site=site.name))

		self.assertEqual(data, [])

	def test_kitchen_included_when_site_linked_to_tender(self):
		company = self._get_company()
		tender_name, tender_price = self._get_existing_tender()
		if not tender_name:
			self.skipTest("No Tender Configuration available in test database")

		site = self._create_site("Tender Site", company=company, tender=tender_name)
		kitchen = self._create_kitchen("Kitchen B", site.name, company=company)
		frappe.db.set_value(
			"Project",
			kitchen.name,
			"total_purchase_cost",
			200,
			update_modified=False,
		)

		data = get_data(self._report_filters(company, site=site.name))

		row = next((item for item in data if item["kitchen_unit"] == kitchen.name), None)
		self.assertIsNotNone(row)
		self.assertEqual(row["site"], site.name)
		self.assertEqual(row["tender_configuration"], tender_name)
		self.assertAlmostEqual(flt(row["tender_price_per_kitchen"]), flt(tender_price), places=2)
		self.assertEqual(row["total_purchase_cost"], 200)
		self.assertEqual(row["total_cost"], 200)

	def test_zero_cost_kitchen_included_when_site_linked_to_tender(self):
		company = self._get_company()
		tender_name, tender_price = self._get_existing_tender()
		if not tender_name:
			self.skipTest("No Tender Configuration available in test database")

		site = self._create_site("Zero Cost Tender Site", company=company, tender=tender_name)
		kitchen_with_cost = self._create_kitchen("Kitchen With Cost", site.name, company=company)
		kitchen_zero_cost = self._create_kitchen("Kitchen Zero Cost", site.name, company=company)
		frappe.db.set_value(
			"Project",
			kitchen_with_cost.name,
			"total_purchase_cost",
			150,
			update_modified=False,
		)

		data = get_data(self._report_filters(company, site=site.name))
		kitchen_units = {row["kitchen_unit"] for row in data}

		self.assertIn(kitchen_with_cost.name, kitchen_units)
		self.assertIn(kitchen_zero_cost.name, kitchen_units)

		zero_row = next(row for row in data if row["kitchen_unit"] == kitchen_zero_cost.name)
		self.assertEqual(zero_row["total_cost"], 0)
		self.assertAlmostEqual(flt(zero_row["profit_margin"]), flt(tender_price), places=2)

	def test_kitchen_status_fields_included(self):
		company = self._get_company()
		tender_name, _tender_price = self._get_existing_tender()
		if not tender_name:
			self.skipTest("No Tender Configuration available in test database")

		site = self._create_site("Status Site", company=company, tender=tender_name)
		kitchen = self._create_kitchen("Kitchen Status", site.name, company=company)
		frappe.db.set_value("Project", kitchen.name, "status", "Open", update_modified=False)

		data = get_data(self._report_filters(company, site=site.name))
		row = next(item for item in data if item["kitchen_unit"] == kitchen.name)

		self.assertEqual(row["kitchen_status"], "Open")
		self.assertEqual(row["is_kitchen_completed"], 0)

	def test_get_kitchen_completion_by_site_requires_all_completed(self):
		company = self._get_company()
		tender_name, _tender_price = self._get_existing_tender()
		if not tender_name:
			self.skipTest("No Tender Configuration available in test database")

		site = self._create_site("Completion Site", company=company, tender=tender_name)
		kitchen_a = self._create_kitchen("Kitchen A Complete", site.name, company=company)
		kitchen_b = self._create_kitchen("Kitchen B Open", site.name, company=company)
		frappe.db.set_value("Project", kitchen_a.name, "status", "Completed", update_modified=False)
		frappe.db.set_value("Project", kitchen_b.name, "status", "Open", update_modified=False)

		completed_sites = _get_kitchen_completion_by_site([site.name])
		self.assertNotIn(site.name, completed_sites)

		frappe.db.set_value("Project", kitchen_b.name, "status", "Completed", update_modified=False)
		completed_sites = _get_kitchen_completion_by_site([site.name])
		self.assertIn(site.name, completed_sites)

	def test_filter_work_orders_by_date(self):
		from_date = getdate(today())
		to_date = add_days(from_date, 30)
		work_orders = [
			frappe._dict(
				name="WO-1",
				planned_start_date=add_days(from_date, 5),
				creation=from_date,
			),
			frappe._dict(
				name="WO-2",
				planned_start_date=add_days(from_date, 40),
				creation=from_date,
			),
		]

		filtered = filter_work_orders_by_date(work_orders, from_date, to_date)

		self.assertEqual([row.name for row in filtered], ["WO-1"])

	def test_manufacturing_actual_cost_respects_date_filter(self):
		company = self._get_company()
		kitchen = self._create_kitchen("Kitchen Mfg", None, company=company)
		work_order = self._create_work_order(
			kitchen.name,
			company=company,
			planned_start_date=add_days(today(), -10),
		)
		self._create_job_card(work_order, hour_rate=60, minutes=120)

		in_range = get_manufacturing_actual_cost_by_project(
			[kitchen.name],
			add_days(today(), -30),
			today(),
		)
		out_of_range = get_manufacturing_actual_cost_by_project(
			[kitchen.name],
			add_days(today(), -60),
			add_days(today(), -31),
		)

		self.assertEqual(in_range.get(kitchen.name), 120)
		self.assertEqual(out_of_range.get(kitchen.name, 0), 0)

	def _create_job_card(self, work_order, hour_rate, minutes):
		operation = work_order.operations[0].operation if work_order.operations else None
		workstation = work_order.operations[0].workstation if work_order.operations else None
		if not operation:
			operation = frappe.db.get_value("Operation", {}, "name")
		if not workstation:
			workstation = frappe.db.get_value("Workstation", {}, "name")

		doc = frappe.get_doc(
			{
				"doctype": "Job Card",
				"work_order": work_order.name,
				"operation": operation,
				"workstation": workstation,
				"hour_rate": hour_rate,
				"total_time_in_mins": minutes,
				"for_quantity": work_order.qty or 1,
			}
		)
		doc.set_new_name()
		doc.db_insert()
		time_log = frappe.get_doc(
			{
				"doctype": "Job Card Time Log",
				"parent": doc.name,
				"parenttype": "Job Card",
				"parentfield": "time_logs",
				"time_in_mins": minutes,
				"idx": 1,
			}
		)
		time_log.set_new_name()
		time_log.db_insert()
		return doc

	def test_get_data_requires_site_project(self):
		company = self._get_company()
		self.assertEqual(get_data(self._report_filters(company)), [])

	def _report_filters(self, company, site=None):
		from_date = add_days(today(), -365)
		to_date = add_days(today(), 365)
		filters = frappe._dict(
			company=company,
			from_date=from_date,
			to_date=to_date,
		)
		if site:
			filters.site_project = site
		return filters

	def _get_company(self):
		company = frappe.defaults.get_defaults().company
		if not company:
			company = frappe.db.get_value("Company", {}, "name")
		return company

	def _get_existing_tender(self):
		row = frappe.get_all(
			"Tender Configuration",
			fields=["name", "tender_price_per_kitchen"],
			limit=1,
		)
		if not row:
			return None, None
		return row[0].name, row[0].tender_price_per_kitchen

	def _insert_project(self, values):
		doc = frappe.get_doc(values)
		doc.naming_series = get_naming_series_for_project_type(doc.project_type)
		doc.set_new_name()
		doc.db_insert()
		return doc

	def _create_site(self, project_name, company, tender=None):
		return self._insert_project(
			{
				"doctype": "Project",
				"project_name": project_name,
				"project_type": "Site",
				"company": company,
				"fk_tender_configuration": tender,
			}
		)

	def _create_kitchen(self, project_name, site, company, **kwargs):
		values = {
			"doctype": "Project",
			"project_name": project_name,
			"project_type": "Kitchen",
			"company": company,
			**kwargs,
		}
		if site:
			values["fk_parent_project"] = site
		return self._insert_project(values)

	def _create_work_order(self, project, company, planned_start_date=None):
		item = frappe.db.get_value("Item", {"is_stock_item": 1}, "name")
		if not item:
			item = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": f"TEST-ITEM-{frappe.generate_hash(length=6)}",
					"item_name": "Test Item",
					"item_group": "Products",
					"stock_uom": "Nos",
				}
			).insert(ignore_permissions=True).name

		bom = frappe.db.get_value("BOM", {"item": item, "is_active": 1}, "name")
		if not bom:
			bom_doc = frappe.get_doc(
				{
					"doctype": "BOM",
					"item": item,
					"quantity": 1,
					"company": company,
				}
			)
			bom_doc.append("items", {"item_code": item, "qty": 1, "rate": 10})
			bom_doc.insert(ignore_permissions=True)
			bom = bom_doc.name

		return frappe.get_doc(
			{
				"doctype": "Work Order",
				"production_item": item,
				"bom_no": bom,
				"qty": 1,
				"company": company,
				"project": project,
				"planned_start_date": planned_start_date or today(),
			}
		).insert(ignore_permissions=True)


def flt(value):
	from frappe.utils import flt as _flt

	return _flt(value)
