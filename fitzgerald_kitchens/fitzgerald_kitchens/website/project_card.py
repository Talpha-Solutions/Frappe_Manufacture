# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today

from fitzgerald_kitchens.fitzgerald_kitchens.utils.stage_tracking import STAGE_SCHEDULE_INDICATORS

EXCLUDED_TASK_STATUSES = ("Cancelled", "Template")


def _set_project_stage(project, stage_name, schedule_status):
	project.current_stage = stage_name
	project.current_stage_schedule = schedule_status
	project.current_stage_schedule_indicator = STAGE_SCHEDULE_INDICATORS.get(schedule_status, "gray")


def _clear_project_stage(project):
	project.current_stage = None
	project.current_stage_schedule = None
	project.current_stage_schedule_indicator = None


def _task_sort_key(task):
	return (task.creation or "", task.idx or 0)


def get_current_task_row(tasks):
	"""Return the task after the latest completed task in the project task list."""
	if not tasks:
		return None

	sorted_tasks = sorted(tasks, key=_task_sort_key)
	last_completed_index = None

	for index, task in enumerate(sorted_tasks):
		if task.status == "Completed":
			last_completed_index = index

	if last_completed_index is None:
		return sorted_tasks[0]

	next_index = last_completed_index + 1
	if next_index < len(sorted_tasks):
		return sorted_tasks[next_index]

	return sorted_tasks[last_completed_index]


def get_task_schedule_status(task) -> str | None:
	"""Compare today against Expected End Date only."""
	if not task or not task.exp_end_date:
		return None

	expected_date = getdate(task.exp_end_date)
	today_date = getdate(today())

	if today_date < expected_date:
		return "Early"
	if today_date > expected_date:
		return "Late"
	return "On Time"


def enrich_projects_with_current_stage(projects) -> None:
	"""Add current task stage + schedule pill data to project website list rows."""
	if not projects:
		return

	project_names = [project.name for project in projects]
	for project in projects:
		_clear_project_stage(project)

	tasks = frappe.get_all(
		"Task",
		filters={
			"project": ["in", project_names],
			"status": ["not in", list(EXCLUDED_TASK_STATUSES)],
		},
		fields=[
			"name",
			"subject",
			"project",
			"status",
			"exp_end_date",
			"idx",
			"creation",
		],
		order_by="creation asc, idx asc",
	)

	tasks_by_project = {}
	for task in tasks:
		tasks_by_project.setdefault(task.project, []).append(task)

	for project in projects:
		current_task = get_current_task_row(tasks_by_project.get(project.name, []))
		if not current_task:
			continue

		_set_project_stage(
			project,
			current_task.subject or current_task.name,
			get_task_schedule_status(current_task),
		)


# Backwards compatibility for earlier imports
enrich_projects_with_current_task = enrich_projects_with_current_stage
