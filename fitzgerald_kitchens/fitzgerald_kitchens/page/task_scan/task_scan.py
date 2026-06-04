# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.my_tasks import (
	_assignees_from_task_row,
	_check_my_tasks_access,
)


def _format_relative_due(exp_end_date) -> tuple[str, str]:
	"""Return (display label, css class) e.g. Today · 27 May."""
	if not exp_end_date:
		return _("No due date"), ""

	exp = getdate(exp_end_date)
	today_date = getdate(today())
	delta = (exp - today_date).days

	if exp.year != today_date.year:
		date_part = frappe.utils.formatdate(exp, "d MMM yyyy")
	else:
		date_part = frappe.utils.formatdate(exp, "d MMM")

	if delta == 0:
		relative = _("Today")
	elif delta == 1:
		relative = _("Tomorrow")
	elif delta == -1:
		relative = _("Yesterday")
	else:
		relative = frappe.utils.formatdate(exp, "dddd")

	return f"{relative} · {date_part}", ""


def _due_badge(task) -> tuple[str, str]:
	"""Header pill text and class (due-today, overdue)."""
	if task.status == "Completed":
		return _("Completed"), ""
	if not task.exp_end_date:
		return _("No due date"), ""

	exp = getdate(task.exp_end_date)
	today_date = getdate(today())
	if exp < today_date:
		return _("Overdue"), "overdue"
	if exp == today_date:
		return _("Due today"), "due-today"
	if exp == add_days(today_date, 1):
		return _("Due tomorrow"), ""
	return _("Upcoming"), ""


def _format_started_display(task) -> str:
	"""Expected / actual start from Task (exp_start_date preferred)."""
	start = task.exp_start_date or task.act_start_date
	if not start:
		return "—"

	dt = frappe.utils.get_datetime(start)
	if dt and dt.hour == 0 and dt.minute == 0 and dt.second == 0:
		return frappe.utils.formatdate(getdate(start), "d MMM")
	return frappe.utils.format_datetime(dt, "d MMM · hh:mm a")


def _get_assignee_names(task_name: str, assign_field) -> list[str]:
	names: list[str] = []
	seen: set[str] = set()

	try:
		from frappe.desk.form.assign_to import get as get_assignments

		for entry in get_assignments({"doctype": "Task", "name": task_name}) or []:
			user_id = entry.get("owner") or entry.get("allocated_to")
			if not user_id or user_id in seen:
				continue
			seen.add(user_id)
			names.append(entry.get("owner_name") or frappe.db.get_value("User", user_id, "full_name") or user_id)
	except Exception:
		pass

	for user_id in _assignees_from_task_row(assign_field):
		if user_id in seen:
			continue
		seen.add(user_id)
		if frappe.db.exists("User", user_id):
			names.append(frappe.db.get_value("User", user_id, "full_name") or user_id)
		else:
			names.append(user_id)

	for row in frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Task",
			"reference_name": task_name,
			"status": ["in", ["Open", "Working"]],
		},
		fields=["allocated_to"],
	):
		user_id = row.allocated_to
		if not user_id or user_id in seen:
			continue
		seen.add(user_id)
		names.append(frappe.db.get_value("User", user_id, "full_name") or user_id)

	return names


def _get_task_header(task_name: str) -> dict:
	if not frappe.db.exists("Task", task_name):
		frappe.throw(_("Task not found"), frappe.DoesNotExistError)

	task = frappe.db.get_value(
		"Task",
		task_name,
		[
			"name",
			"subject",
			"project",
			"status",
			"type",
			"exp_end_date",
			"exp_start_date",
			"act_start_date",
			"_assign",
		],
		as_dict=True,
	)

	if not frappe.has_permission("Task", doc=task_name, ptype="read"):
		frappe.throw(_("Not permitted to access this task"), frappe.PermissionError)

	project_label = None
	unit_subtitle = None
	if task.project:
		project = frappe.db.get_value(
			"Project",
			task.project,
			["project_name", "customer"],
			as_dict=True,
		)
		if project:
			project_label = project.project_name or task.project
			unit_subtitle = project.customer or task.project

	due_display, _due_css = _format_relative_due(task.exp_end_date)
	due_badge_text, due_badge_class = _due_badge(task)
	assignees = _get_assignee_names(task.name, task._assign)

	return {
		"task": task.name,
		"title": task.subject or task.name,
		"subtitle": unit_subtitle or project_label or "",
		"project_label": project_label,
		"task_type": task.type or "—",
		"due_label": due_display,
		"due_badge": due_badge_text,
		"due_class": due_badge_class,
		"started_label": _format_started_display(task),
		"assigned_to": ", ".join(assignees) if assignees else _("Unassigned"),
		"status": task.status,
	}


@frappe.whitelist()
def get_task_scan_context(task: str):
	_check_my_tasks_access()
	header = _get_task_header(task)

	# Label scan stats remain demo until wired
	return {
		**header,
		"total_labels": 22,
		"scanned": 12,
		"outstanding": 9,
		"errors": 1,
		"printed": 22,
		"print_banner": _(
			"22 of 22 labels printed. Last print run: today 13:05 by Cathal F. on Workshop B printer."
		),
		"labels": [
			{"id": "LBL-001", "status": "scanned"},
			{"id": "LBL-002", "status": "scanned"},
			{"id": "LBL-003", "status": "outstanding"},
			{"id": "LBL-004", "status": "error"},
			{"id": "LBL-005", "status": "scanned"},
			{"id": "LBL-006", "status": "outstanding"},
		],
	}
