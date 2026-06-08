# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from fitzgerald_kitchens.fitzgerald_kitchens.website.production_tracker import (
	_ensure_focused_project_in_list,
	_filter_projects_to_site_units,
	_resolve_focused_project,
	_site_focus_search_term,
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

	def test_resolve_focused_site_project_uses_search_not_single_project_focus(self):
		site = self._create_project("Site 005", project_type="Site")

		focused = _resolve_focused_project(site.name)

		self.assertTrue(focused["is_site"])
		self.assertEqual(focused["initial_search"], "Site 005")

	def test_site_focus_search_term_uses_full_site_name(self):
		self.assertEqual(_site_focus_search_term("Site 005"), "Site 005")
		self.assertEqual(_site_focus_search_term("Riverside Site"), "Riverside Site")

	def test_filter_projects_to_site_units_matches_children_by_name(self):
		site = self._create_project("Site 005", project_type="Site")
		unit = self._create_project("Unit 1 | Kitchen | Site 005", project_type="Kitchen")
		other = self._create_project("Unit 2 | Kitchen | Site 006", project_type="Kitchen")
		focused = _resolve_focused_project(site.name)

		filtered = _filter_projects_to_site_units([site, unit, other], focused)

		self.assertEqual([row.name for row in filtered], [unit.name])

	def test_ensure_focused_site_project_is_not_appended_to_tracker_list(self):
		site = self._create_project("Site 005", project_type="Site")
		focused = _resolve_focused_project(site.name)
		active_projects = []

		projects = _ensure_focused_project_in_list(active_projects, focused)

		self.assertEqual(projects, [])

	def _create_project(self, project_name: str, status: str = "Open", project_type: str = "Kitchen"):
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": project_name,
				"status": status,
				"project_type": project_type,
			}
		).insert(ignore_permissions=True)
		return project
