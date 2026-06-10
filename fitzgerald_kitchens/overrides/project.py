# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from fitzgerald_kitchens.workbook_import.naming import (
	format_task_subject_with_unit_context,
	unit_context_label_for_project,
)

try:
	from hrms.overrides.employee_project import EmployeeProject as _ProjectBase
except ImportError:
	from erpnext.projects.doctype.project.project import Project as _ProjectBase


class Project(_ProjectBase):
	def create_task_from_template(self, task_details):
		unit_label = unit_context_label_for_project(self)
		if unit_label:
			task_details.subject = format_task_subject_with_unit_context(
				task_details.subject,
				unit_label,
			)
		return super().create_task_from_template(task_details)
