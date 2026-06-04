# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today

from fitzgerald_kitchens.fitzgerald_kitchens.website.project_card import (
	enrich_tasks_with_schedule_status,
	get_task_schedule_display,
)

MY_TASKS_ROLES = frozenset(
	{
		"My Tasks User",
		"Projects User",
		"Projects Manager",
		"System Manager",
		"Administrator",
	}
)

COMPLETED_STATUS = "Completed"
CANCELLED_STATUSES = ("Cancelled", "Template")


def _check_my_tasks_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.PermissionError)

	if not MY_TASKS_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(_("Not permitted to access My Tasks"), frappe.PermissionError)


def _assignees_from_task_row(assign_field) -> list[str]:
	if not assign_field:
		return []
	try:
		assignees = frappe.parse_json(assign_field)
	except Exception:
		return []
	if isinstance(assignees, str):
		try:
			assignees = frappe.parse_json(assignees)
		except Exception:
			return [assignees] if assignees else []
	if not isinstance(assignees, list):
		return []
	return [entry for entry in assignees if entry]


def _collect_assigned_task_names(user: str) -> list[str]:
	"""Tasks assigned via ToDo (any status) or Task._assign."""
	names: set[str] = set()

	for name in frappe.get_all(
		"ToDo",
		filters={"allocated_to": user, "reference_type": "Task"},
		pluck="reference_name",
		distinct=True,
	):
		if name:
			names.add(name)

	for row in frappe.get_all(
		"Task",
		filters={"_assign": ["is", "set"]},
		fields=["name", "_assign"],
	):
		if user in _assignees_from_task_row(row._assign):
			names.add(row.name)

	return list(names)


def _load_tasks(task_names: list[str]) -> list[dict]:
	if not task_names:
		return []

	tasks = frappe.get_all(
		"Task",
		filters={"name": ["in", task_names]},
		fields=[
			"name",
			"subject",
			"project",
			"status",
			"type",
			"progress",
			"exp_end_date",
			"completed_on",
			"modified",
			"description",
		],
		order_by="exp_end_date asc, modified desc",
	)

	project_names = {task.project for task in tasks if task.project}
	project_labels = {}
	if project_names:
		for row in frappe.get_all(
			"Project",
			filters={"name": ["in", list(project_names)]},
			fields=["name", "project_name", "customer"],
		):
			project_labels[row.name] = row

	enrich_tasks_with_schedule_status(tasks)
	from fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer import enrich_tasks_with_timer

	enrich_tasks_with_timer(tasks, frappe.session.user)

	for task in tasks:
		project = project_labels.get(task.project) if task.project else None
		task.project_label = (project.project_name or task.project) if project else None
		task.unit_subtitle = project.customer if project and project.customer else task.project

		schedule_label, _indicator = get_task_schedule_display(task)
		task.due_label = _due_label(task, schedule_label)
		task.badge_type = task.type or _("Task")
		task.image_count = _task_image_count(task.name)
		task.scanned_label = None

	readable = []
	for task in tasks:
		try:
			if frappe.has_permission("Task", doc=task.name, ptype="read"):
				readable.append(task)
		except Exception:
			continue
	return readable


def _task_image_count(task_name: str) -> int:
	return frappe.db.count(
		"File",
		{
			"attached_to_doctype": "Task",
			"attached_to_name": task_name,
		},
	)


def _due_label(task, schedule_label: str | None) -> str | None:
	if task.status == COMPLETED_STATUS:
		return _("Completed")
	if not task.exp_end_date:
		return None

	exp = getdate(task.exp_end_date)
	today_date = getdate(today())
	if exp == today_date:
		return _("DUE Today")
	if exp < today_date:
		return _("Overdue")
	if schedule_label:
		return schedule_label
	return _("Upcoming")


def _bucket_tasks(tasks: list[dict]) -> dict:
	today_date = getdate(today())
	buckets = {
		"today": [],
		"overdue": [],
		"upcoming": [],
		"completed": [],
	}

	for task in tasks:
		if task.status == COMPLETED_STATUS:
			buckets["completed"].append(task)
			continue
		if task.status in CANCELLED_STATUSES:
			continue

		exp = getdate(task.exp_end_date) if task.exp_end_date else None
		if exp and exp < today_date:
			buckets["overdue"].append(task)
		elif exp and exp == today_date:
			buckets["today"].append(task)
		else:
			buckets["upcoming"].append(task)

	return buckets


def _is_completed_today(task, today_date) -> bool:
	if task.completed_on and getdate(task.completed_on) == today_date:
		return True
	if not task.completed_on and task.modified and getdate(task.modified) == today_date:
		return True
	return False


def _kpis(buckets: dict) -> dict:
	today_date = getdate(today())
	completed_today = sum(
		1 for task in buckets["completed"] if _is_completed_today(task, today_date)
	)

	return {
		"completed_today": completed_today,
		"due_today": len(buckets["today"]),
		"overdue": len(buckets["overdue"]),
	}


def _user_header() -> dict:
	user = frappe.session.user
	full_name = frappe.db.get_value("User", user, "full_name") or user
	user_image = frappe.db.get_value("User", user, "user_image")
	department = None
	employee = frappe.db.get_value("Employee", {"user_id": user}, ["department", "designation"], as_dict=True)
	if employee:
		department = employee.department or employee.designation

	return {
		"email": user,
		"full_name": full_name,
		"user_image": user_image,
		"abbr": frappe.utils.get_abbr(full_name),
		"department": department or _("Worker"),
		"date_label": frappe.utils.formatdate(today(), "ddd d MMM"),
	}


@frappe.whitelist()
def get_my_tasks_dashboard():
	_check_my_tasks_access()
	user = frappe.session.user

	tasks = _load_tasks(_collect_assigned_task_names(user))
	buckets = _bucket_tasks(tasks)

	def serialize_task(task):
		return {
			"name": task.name,
			"subject": task.subject or task.name,
			"project": task.project,
			"project_label": task.project_label,
			"unit_subtitle": task.unit_subtitle,
			"status": task.status,
			"type": task.badge_type,
			"progress": task.progress or 0,
			"exp_end_date": task.exp_end_date,
			"due_label": task.due_label,
			"schedule_indicator": task.schedule_indicator,
			"image_count": task.image_count,
			"scanned_label": task.scanned_label,
			"timer_running": bool(getattr(task, "timer_running", False)),
			"timer_paused": bool(getattr(task, "timer_paused", False)),
			"timer_started_at": getattr(task, "timer_started_at", None),
			"timer_started_at_epoch": getattr(task, "timer_started_at_epoch", None),
			"timer_elapsed_seconds": getattr(task, "timer_elapsed_seconds", 0),
			"timer_expected_hours": getattr(task, "timer_expected_hours", None),
			"total_logged_hours": getattr(task, "total_logged_hours", 0),
			"timesheet_logs": getattr(task, "timesheet_logs", []) or [],
		}

	return {
		"user": _user_header(),
		"kpis": _kpis(buckets),
		"tabs": {
			key: {
				"count": len(items),
				"tasks": [serialize_task(t) for t in items],
			}
			for key, items in buckets.items()
		},
	}


@frappe.whitelist()
def open_qr_scan_from_code(qr_text: str):
	"""Resolve QR and return route target for a new Development Unit QR Scan."""
	_check_my_tasks_access()
	from fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_unit_qr_scan.development_unit_qr_scan import (
		resolve_qr_code,
	)

	result = resolve_qr_code(qr_text)
	return {
		"doctype": "Development Unit QR Scan",
		"development_unit": result.get("development_unit"),
		"project": result.get("project"),
	}
