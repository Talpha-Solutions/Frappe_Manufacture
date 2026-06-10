# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from fitzgerald_kitchens.fitzgerald_kitchens.report.all_sites_tender_profit_margin.all_sites_tender_profit_margin import (
	aggregate_site_margin_rows,
	get_data,
)


class TestAllSitesTenderProfitMargin(IntegrationTestCase):
	def test_aggregate_site_margin_rows_sums_kitchen_units(self):
		unit_rows = [
			{
				"site": "PROJ-A",
				"site_name": "Site A",
				"is_site_delayed": 0,
				"tender_configuration": "T-1",
				"tender_name": "Tender A",
				"tender_price_per_kitchen": 1000,
				"manufacturing_actual_cost": 100,
				"task_actual_cost": 50,
				"total_expense_claim": 25,
				"total_purchase_cost": 75,
				"total_consumed_material_cost": 50,
				"total_cost": 300,
				"profit_margin": 700,
				"cost_variance": -700,
				"margin_pct": 70,
			},
			{
				"site": "PROJ-A",
				"site_name": "Site A",
				"is_site_delayed": 0,
				"tender_configuration": "T-1",
				"tender_name": "Tender A",
				"tender_price_per_kitchen": 1000,
				"manufacturing_actual_cost": 200,
				"task_actual_cost": 0,
				"total_expense_claim": 0,
				"total_purchase_cost": 100,
				"total_consumed_material_cost": 0,
				"total_cost": 300,
				"profit_margin": 700,
				"cost_variance": -700,
				"margin_pct": 70,
			},
			{
				"site": "PROJ-B",
				"site_name": "Site B",
				"is_site_delayed": 1,
				"tender_configuration": "T-2",
				"tender_name": "Tender B",
				"tender_price_per_kitchen": 500,
				"manufacturing_actual_cost": 400,
				"task_actual_cost": 100,
				"total_expense_claim": 0,
				"total_purchase_cost": 0,
				"total_consumed_material_cost": 0,
				"total_cost": 500,
				"profit_margin": 0,
				"cost_variance": 0,
				"margin_pct": 0,
			},
		]

		data = aggregate_site_margin_rows(unit_rows)

		self.assertEqual(len(data), 2)
		site_a = next(row for row in data if row["site"] == "PROJ-A")
		site_b = next(row for row in data if row["site"] == "PROJ-B")

		self.assertEqual(site_a["kitchen_count"], 2)
		self.assertEqual(site_a["total_cost"], 600)
		self.assertEqual(site_a["total_tender_budget"], 0)
		self.assertEqual(site_a["profit_margin"], -600)

		self.assertEqual(site_b["kitchen_count"], 1)
		self.assertEqual(site_b["total_cost"], 500)
		self.assertEqual(site_b["total_tender_budget"], 0)
		self.assertEqual(site_b["profit_margin"], -500)
		self.assertEqual(site_b["is_site_delayed"], 1)

	def test_aggregate_site_margin_rows_includes_sites_without_cost(self):
		unit_rows = [
			{
				"site": "PROJ-A",
				"site_name": "Site A",
				"is_site_delayed": 0,
				"tender_configuration": "T-1",
				"tender_name": "Tender A",
				"tender_price_per_kitchen": 1000,
				"manufacturing_actual_cost": 100,
				"task_actual_cost": 0,
				"total_expense_claim": 0,
				"total_purchase_cost": 0,
				"total_consumed_material_cost": 0,
				"total_cost": 100,
				"profit_margin": 900,
				"cost_variance": -900,
				"margin_pct": 90,
			}
		]
		all_sites = [
			frappe._dict(
				name="PROJ-A",
				project_name="Site A",
				fk_tender_configuration="T-1",
			),
			frappe._dict(
				name="PROJ-B",
				project_name="Site B",
				fk_tender_configuration="",
			),
		]

		data = aggregate_site_margin_rows(unit_rows, all_sites)

		self.assertEqual(len(data), 2)
		site_b = next(row for row in data if row["site"] == "PROJ-B")
		self.assertEqual(site_b["total_cost"], 0)
		self.assertEqual(site_b["tender_configuration"], "")
		self.assertEqual(site_b["profit_margin"], 0)

	def test_get_data_returns_empty_without_company(self):
		self.assertEqual(get_data({}), [])

	def tearDown(self):
		frappe.db.rollback()
