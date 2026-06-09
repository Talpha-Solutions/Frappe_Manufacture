# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer import OPEN_STATUS, WORKING_STATUS
from fitzgerald_kitchens.fitzgerald_kitchens.page.task_scan.label_scan import (
	get_task_label_scan_state,
	is_label_scan_task_type,
)
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
ONGOING_TASK_STATUSES = frozenset({WORKING_STATUS, "Pending Review"})


def _check_my_tasks_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.PermissionError)

	if not MY_TASKS_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(_("Not permitted to access My Tasks"), frappe.PermissionError)


def _normalize_assignee_entry(entry) -> str | None:
	if not entry:
		return None
	if isinstance(entry, dict):
		return entry.get("owner") or entry.get("allocated_to") or entry.get("user")
	if isinstance(entry, str):
		return entry.strip() or None
	return str(entry)


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
			user_id = _normalize_assignee_entry(assignees)
			return [user_id] if user_id else []
	if not isinstance(assignees, list):
		user_id = _normalize_assignee_entry(assignees)
		return [user_id] if user_id else []

	user_ids = []
	for entry in assignees:
		user_id = _normalize_assignee_entry(entry)
		if user_id:
			user_ids.append(user_id)
	return user_ids


def get_task_assignee_labels(
	task_name: str,
	*,
	completed_by: str | None = None,
	assign_field=None,
) -> list[str]:
	"""Resolve Task assignees from _assign, open ToDos, and completed_by."""
	user_ids: list[str] = []
	seen: set[str] = set()

	def add_user(user_id: str | None) -> None:
		if not user_id or user_id in seen:
			return
		seen.add(user_id)
		user_ids.append(user_id)

	if assign_field is None:
		assign_field = frappe.db.get_value("Task", task_name, "_assign")

	for user_id in _assignees_from_task_row(assign_field):
		add_user(user_id)

	try:
		for user_id in frappe.get_doc("Task", task_name).get_assigned_users() or []:
			add_user(user_id)
	except Exception:
		pass

	for user_id in frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Task",
			"reference_name": task_name,
			"allocated_to": ["is", "set"],
		},
		pluck="allocated_to",
		distinct=True,
	):
		add_user(user_id)

	if completed_by:
		add_user(completed_by)

	labels = []
	for user_id in user_ids:
		labels.append(frappe.db.get_value("User", user_id, "full_name") or user_id)
	return labels


def get_task_assignee_display(
	task_name: str,
	*,
	completed_by: str | None = None,
	assign_field=None,
) -> str:
	labels = get_task_assignee_labels(
		task_name,
		completed_by=completed_by,
		assign_field=assign_field,
	)
	return ", ".join(labels) if labels else _("Unassigned")


def _collect_assigned_task_names(user: str) -> list[str]:
	"""Tasks explicitly assigned to the user via ToDo or Task._assign."""
	names: set[str] = set()

	for name in frappe.get_all(
		"ToDo",
		filters={
			"allocated_to": user,
			"reference_type": "Task",
			"status": ["!=", "Cancelled"],
		},
		pluck="reference_name",
		distinct=True,
	):
		if name and frappe.db.exists("Task", name):
			names.add(name)

	for row in frappe.get_all(
		"Task",
		filters={"_assign": ["like", f"%{user}%"]},
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
			"exp_start_date",
			"exp_end_date",
			"completed_on",
			"modified",
			"description",
		],
		order_by="exp_start_date asc, exp_end_date asc, modified desc",
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
		if is_label_scan_task_type(task.type):
			scan_state = get_task_label_scan_state(task.name)
			scanned = scan_state.get("scanned") or 0
			total = scan_state.get("total_labels") or 0
			task.scan_scanned = scanned
			task.scan_total = total
			if total:
				task.scanned_label = _("{0}/{1} scanned").format(scanned, total)

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


def _task_start_date(task):
	if task.exp_start_date:
		return getdate(task.exp_start_date)
	return None


def _starts_today(task, today_date) -> bool:
	start = _task_start_date(task)
	return bool(start and start == today_date)


def _started_before_today(task, today_date) -> bool:
	start = _task_start_date(task)
	return bool(start and start < today_date)


def _is_open_task(task) -> bool:
	return task.status == OPEN_STATUS


def _belongs_in_today_tab(task, today_date) -> bool:
	if _is_ongoing_task(task):
		return True
	if _starts_today(task, today_date):
		return True
	if _is_open_task(task) and _started_before_today(task, today_date):
		return True
	return False


def _is_ongoing_task(task) -> bool:
	if task.status in ONGOING_TASK_STATUSES:
		return True
	return bool(getattr(task, "timer_running", False))


def _due_label(task, schedule_label: str | None) -> str | None:
	if task.status == COMPLETED_STATUS:
		return _("Completed")

	today_date = getdate(today())
	start = _task_start_date(task)
	exp_end = getdate(task.exp_end_date) if task.exp_end_date else None

	if exp_end and exp_end < today_date:
		return _("Overdue")
	if start and start == today_date:
		return _("Starts today")
	if start and start > today_date:
		return formatdate(start, "d MMM")
	if exp_end and exp_end == today_date:
		return _("DUE Today")
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

		exp_end = getdate(task.exp_end_date) if task.exp_end_date else None
		start = _task_start_date(task)

		if _belongs_in_today_tab(task, today_date):
			buckets["today"].append(task)
		elif exp_end and exp_end < today_date:
			buckets["overdue"].append(task)
		elif start and start > today_date:
			buckets["upcoming"].append(task)
		else:
			buckets["upcoming"].append(task)

	_sort_bucket_tasks(buckets)
	return buckets


def _sort_bucket_tasks(buckets: dict) -> None:
	def _start_sort_key(task):
		start = task.exp_start_date or "9999-12-31"
		return (start, task.exp_end_date or "9999-12-31", task.modified or "")

	buckets["today"].sort(key=_start_sort_key)
	buckets["upcoming"].sort(key=_start_sort_key)
	buckets["overdue"].sort(
		key=lambda task: (task.exp_end_date or "9999-12-31", task.exp_start_date or "", task.modified or "")
	)


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

	starts_today = sum(
		1
		for bucket_key in ("today", "upcoming", "overdue")
		for task in buckets[bucket_key]
		if _starts_today(task, today_date)
	)

	return {
		"completed_today": completed_today,
		"due_today": starts_today,
		"overdue": len(buckets["overdue"]),
	}


def _assigned_project_options(user: str) -> list[dict]:
	"""Projects linked only to tasks assigned to the logged-in user."""
	task_names = _collect_assigned_task_names(user)
	if not task_names:
		return []

	readable_task_names = [
		name
		for name in task_names
		if frappe.has_permission("Task", doc=name, ptype="read")
	]
	if not readable_task_names:
		return []

	rows = frappe.db.sql(
		"""
		select distinct t.project as name,
			coalesce(nullif(p.project_name, ''), t.project) as label
		from `tabTask` t
		left join `tabProject` p on p.name = t.project
		where t.name in %(task_names)s
			and ifnull(t.project, '') != ''
		order by label asc
		""",
		{"task_names": readable_task_names},
		as_dict=True,
	)
	return rows


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
		"date_label": frappe.utils.formatdate(today(), "EEE d MMM"),
	}


@frappe.whitelist()
def get_my_tasks_dashboard(project: str | None = None):
	_check_my_tasks_access()
	user = frappe.session.user

	all_tasks = _load_tasks(_collect_assigned_task_names(user))
	projects = _assigned_project_options(user)
	allowed_projects = {row["name"] for row in projects}
	if project and project not in allowed_projects:
		project = None

	tasks = all_tasks
	if project:
		tasks = [task for task in all_tasks if task.project == project]

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
			"exp_start_date": task.exp_start_date,
			"exp_end_date": task.exp_end_date,
			"due_label": task.due_label,
			"schedule_indicator": task.schedule_indicator,
			"image_count": task.image_count,
			"scanned_label": task.scanned_label,
			"scan_scanned": getattr(task, "scan_scanned", 0),
			"scan_total": getattr(task, "scan_total", 0),
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
		"project_filter": project or "",
		"projects": projects,
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
