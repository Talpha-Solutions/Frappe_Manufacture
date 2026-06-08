# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from fitzgerald_kitchens.manufacturing.project_manifest import (
	get_manifest_items_for_project,
	get_projects_for_production_plan,
	is_manufacturing_item,
)


class TestProductionPlanProjects(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name") or "_Test Company"
		cls.ensure_company()

	@classmethod
	def ensure_company(cls):
		if not frappe.db.exists("Company", cls.company):
			from erpnext.setup.utils import enable_all_roles_and_domains

			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": cls.company,
					"abbr": "TC",
					"default_currency": "USD",
					"country": "United States",
				}
			).insert(ignore_permissions=True)
			enable_all_roles_and_domains()

	def tearDown(self):
		frappe.db.rollback()

	def test_get_open_projects_and_items(self):
		item_code = self._create_item_with_bom("PP Test FG Item")
		manifest = self._create_manifest(item_code)
		project = self._create_project("PP Test Kitchen", manifest.name)

		plan = self._new_production_plan(project=project.name)
		plan.get_open_projects()
		self.assertEqual(len(plan.fk_projects), 1)
		self.assertEqual(plan.fk_projects[0].project, project.name)

		plan.get_items()
		self.assertEqual(len(plan.po_items), 1)
		self.assertEqual(plan.po_items[0].item_code, item_code)
		self.assertEqual(plan.po_items[0].planned_qty, 2)
		self.assertEqual(plan.po_items[0].fk_project, project.name)

	def test_project_without_manifest_is_skipped(self):
		project = self._create_project("PP Test No Manifest", None)
		plan = self._new_production_plan(project=project.name)
		plan.get_open_projects()

		with self.assertRaises(frappe.ValidationError):
			plan.get_items()

	def test_get_production_items_sets_project(self):
		item_code = self._create_item_with_bom("PP Test WO Item")
		manifest = self._create_manifest(item_code, qty=1)
		project = self._create_project("PP Test WO Kitchen", manifest.name)

		plan = self._new_production_plan()
		plan.append("fk_projects", {"project": project.name})
		plan.get_items()

		production_items = plan.get_production_items()
		self.assertEqual(next(iter(production_items.values()))["project"], project.name)

	def test_raw_material_items_are_excluded(self):
		fg_code = f"PP Test FG {frappe.generate_hash(length=6)}"
		rm_code = f"PP Test RM {frappe.generate_hash(length=6)}"
		self._create_item_with_bom(fg_code)
		if not frappe.db.exists("Item", rm_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": rm_code,
					"item_name": rm_code,
					"item_group": "Raw Material",
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"include_item_in_manufacturing": 0,
				}
			).insert(ignore_permissions=True)

		manifest_code = f"PP-TEST-MANIFEST-{frappe.generate_hash(length=6)}"
		if not frappe.db.exists("Project Unit Configuration", "PP-TEST-CONFIG"):
			frappe.get_doc(
				{
					"doctype": "Project Unit Configuration",
					"configuration_code": "PP-TEST-CONFIG",
					"configuration_name": "PP Test Config",
					"scope": "Project Template",
				}
			).insert(ignore_permissions=True)

		manifest = frappe.get_doc(
			{
				"doctype": "Manifest",
				"manifest_code": manifest_code,
				"scope": "Project Template",
				"manifest_category": "Kitchen",
				"configuration": "PP-TEST-CONFIG",
				"items": [
					{"item_code": fg_code, "qty": 1, "uom": "Nos"},
					{"item_code": rm_code, "qty": 5, "uom": "Nos"},
				],
			}
		)
		manifest.insert(ignore_permissions=True)
		project = self._create_project("PP Test RM Filter Kitchen", manifest.name)

		items = get_manifest_items_for_project(project.name)
		self.assertEqual([row["item_code"] for row in items], [fg_code])
		self.assertFalse(is_manufacturing_item(rm_code))

	def _create_item_with_bom(self, item_code: str) -> str:
		rm_item_code = f"{item_code}-RM"
		for code, is_fg in ((rm_item_code, False), (item_code, True)):
			if frappe.db.exists("Item", code):
				continue

			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": "Products",
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"include_item_in_manufacturing": 1 if is_fg else 0,
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("BOM", {"item": item_code, "is_default": 1}):
			bom = frappe.get_doc(
				{
					"doctype": "BOM",
					"item": item_code,
					"company": self.company,
					"quantity": 1,
					"is_active": 1,
					"is_default": 1,
					"items": [{"item_code": rm_item_code, "qty": 1, "uom": "Nos"}],
				}
			)
			bom.insert(ignore_permissions=True)
			bom.submit()

		return item_code

	def _new_production_plan(self, **kwargs):
		plan = frappe.new_doc("Production Plan")
		plan.update(
			{
				"company": self.company,
				"posting_date": nowdate(),
				"get_items_from": "Project",
				**kwargs,
			}
		)
		return plan

	def _create_manifest(self, item_code: str, qty: float = 2):
		manifest_code = f"PP-TEST-MANIFEST-{frappe.generate_hash(length=6)}"
		if not frappe.db.exists("Project Unit Configuration", "PP-TEST-CONFIG"):
			frappe.get_doc(
				{
					"doctype": "Project Unit Configuration",
					"configuration_code": "PP-TEST-CONFIG",
					"configuration_name": "PP Test Config",
					"scope": "Project Template",
				}
			).insert(ignore_permissions=True)

		manifest = frappe.get_doc(
			{
				"doctype": "Manifest",
				"manifest_code": manifest_code,
				"scope": "Project Template",
				"manifest_category": "Kitchen",
				"configuration": "PP-TEST-CONFIG",
				"items": [{"item_code": item_code, "qty": qty, "uom": "Nos"}],
			}
		)
		manifest.insert(ignore_permissions=True)
		return manifest

	def _create_project(self, project_name: str, manifest_name: str | None):
		project_type = "Kitchen"
		if not frappe.db.exists("Project Type", project_type):
			frappe.get_doc({"doctype": "Project Type", "project_type": project_type}).insert(
				ignore_permissions=True
			)

		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": project_name,
				"company": self.company,
				"project_type": project_type,
				"expected_start_date": nowdate(),
				"fk_effective_manifest": manifest_name,
			}
		)
		project.insert(ignore_permissions=True)
		return project
