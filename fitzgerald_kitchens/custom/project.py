# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, cint, getdate, today

try:
	from hrms.overrides.employee_project import EmployeeProject as ProjectBase
except ImportError:
	from erpnext.projects.doctype.project.project import Project as ProjectBase


class FKProject(ProjectBase):
	def copy_from_template(self):
		if self.project_template and not frappe.db.get_all("Task", {"project": self.name}, limit=1):
			if not self.expected_start_date:
				self.expected_start_date = today()

			self._ensure_expected_end_date_for_template()
			self._persist_expected_dates()

		super().copy_from_template()

	def _ensure_expected_end_date_for_template(self):
		template = frappe.get_doc("Project Template", self.project_template)
		project_start = getdate(self.expected_start_date)
		latest_task_end = project_start

		for row in template.tasks:
			task_details = frappe.get_doc("Task", row.task)
			task_end = add_days(project_start, cint(task_details.start) + cint(task_details.duration))
			if getdate(task_end) > latest_task_end:
				latest_task_end = getdate(task_end)

		if not self.expected_end_date or getdate(self.expected_end_date) < latest_task_end:
			self.expected_end_date = latest_task_end

	def _persist_expected_dates(self):
		updates = {}
		if self.expected_start_date:
			updates["expected_start_date"] = self.expected_start_date
		if self.expected_end_date:
			updates["expected_end_date"] = self.expected_end_date

		if updates:
			self.db_set(updates, update_modified=False)
