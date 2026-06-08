# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from fitzgerald_kitchens.fitzgerald_kitchens.website.production_tracker import (
	_ensure_focused_project_in_list,
	_resolve_focused_project,
)


class TestProductionTracker(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_resolve_focused_project_returns_search_label(self):
		project = self._create_project("Tracker Focus Kitchen")

		focused = _resolve_focused_project(project.name)

		self.assertIsNotNone(focused)
		self.assertEqual(focused["name"], project.name)
		self.assertEqual(focused["initial_search"], project.project_name)

	def test_ensure_focused_project_in_list_appends_missing_project(self):
		project = self._create_project("Tracker Completed Kitchen", status="Completed")
		focused = _resolve_focused_project(project.name)
		active_projects = []

		projects = _ensure_focused_project_in_list(active_projects, focused)

		self.assertEqual(len(projects), 1)
		self.assertEqual(projects[0].name, project.name)

	def _create_project(self, project_name: str, status: str = "Open"):
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": project_name,
				"status": status,
				"project_type": "Kitchen",
			}
		).insert(ignore_permissions=True)
		return project
