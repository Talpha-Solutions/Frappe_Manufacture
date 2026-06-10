# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.workbook_import.naming import (
	format_task_subject_with_unit_context,
	unit_context_label_for_project,
)


def execute():
	updated = 0
	tasks = frappe.get_all(
		"Task",
		filters={"template_task": ["is", "set"], "project": ["is", "set"]},
		fields=["name", "subject", "project"],
	)

	for task in tasks:
		project = frappe.db.get_value(
			"Project",
			task.project,
			["name", "project_name", "project_type", "fk_parent_project", "fk_house_number"],
			as_dict=True,
		)
		if not project or not project.fk_parent_project:
			continue

		unit_label = unit_context_label_for_project(project)
		if not unit_label:
			continue

		new_subject = format_task_subject_with_unit_context(task.subject, unit_label)
		if new_subject == task.subject:
			continue

		frappe.db.set_value("Task", task.name, "subject", new_subject, update_modified=False)
		updated += 1

	if updated:
		frappe.db.commit()
