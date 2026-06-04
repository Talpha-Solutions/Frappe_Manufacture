# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, time_diff_in_hours, today

OPEN_STATUS = "Open"
WORKING_STATUS = "Working"
COMPLETED_STATUS = "Completed"
LOCKED_TASK_STATUSES = frozenset({COMPLETED_STATUS, "Cancelled", "Template"})

MY_TASKS_ROLES = frozenset(
	{
		"My Tasks User",
		"Projects User",
		"Projects Manager",
		"System Manager",
		"Administrator",
	}
)


PAUSE_CACHE_PREFIX = "my_tasks_timer_paused"


def _pause_cache_key(user: str, task: str) -> str:
	return f"{PAUSE_CACHE_PREFIX}:{user}:{task}"


def _set_timer_paused(user: str, task: str, paused: bool) -> None:
	key = _pause_cache_key(user, task)
	if paused:
		frappe.cache.set_value(key, 1)
	else:
		frappe.cache.delete_value(key)


def _is_timer_paused(user: str, task: str) -> bool:
	return bool(frappe.cache.get_value(_pause_cache_key(user, task)))


def _check_my_tasks_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.PermissionError)

	if not MY_TASKS_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(_("Not permitted to access My Tasks"), frappe.PermissionError)


def _check_task_access(task_name: str):
	_check_my_tasks_access()
	if not frappe.has_permission("Task", doc=task_name, ptype="read"):
		frappe.throw(_("Not permitted to access this task"), frappe.PermissionError)


def _get_employee(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def _get_default_activity_type() -> str | None:
	name = frappe.db.get_value("Activity Type", {}, "name", order_by="modified desc")
	if name:
		return name
	return frappe.db.get_single_value("Projects Settings", "default_activity_type") or None


def _get_company(task_name: str, project: str | None) -> str:
	if project:
		company = frappe.db.get_value("Project", project, "company")
		if company:
			return company
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def _get_running_time_log(user: str | None = None, task: str | None = None) -> dict | None:
	user = user or frappe.session.user

	rows = frappe.db.sql(
		"""
		select
			td.name as detail_name,
			td.parent as timesheet,
			td.task,
			td.project,
			td.from_time,
			td.expected_hours,
			td.hours,
			ts.name as timesheet_name
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		where ts.docstatus = 0
			and ts.owner = %(user)s
			and td.from_time is not null
			and (td.to_time is null or td.to_time = '')
		{task_clause}
		order by td.from_time desc
		limit 1
		""".format(task_clause="and td.task = %(task)s" if task else ""),
		{"user": user, "task": task},
		as_dict=True,
	)
	return rows[0] if rows else None


def _find_draft_timesheet(
	user: str, employee: str, project: str | None, task: str
) -> str | None:
	"""Reuse the draft timesheet for this employee, project, and task (append rows, do not create another)."""
	rows = frappe.db.sql(
		"""
		select ts.name
		from `tabTimesheet` ts
		inner join `tabTimesheet Detail` td on td.parent = ts.name and td.task = %(task)s
		where ts.docstatus = 0
			and ts.employee = %(employee)s
			and (%(project)s is null or ts.parent_project is null or ts.parent_project = %(project)s)
		order by ts.modified desc
		limit 1
		""",
		{"employee": employee, "task": task, "project": project},
		as_dict=True,
	)
	if rows:
		return rows[0].name

	return None


def _has_draft_timesheet_for_task(user: str, task: str) -> bool:
	return bool(_find_draft_timesheet_name_for_task(user, task))


def _find_draft_timesheet_name_for_task(user: str, task: str) -> str | None:
	rows = frappe.db.sql(
		"""
		select ts.name
		from `tabTimesheet` ts
		inner join `tabTimesheet Detail` td on td.parent = ts.name and td.task = %(task)s
		where ts.docstatus = 0
			and ts.owner = %(user)s
		order by ts.modified desc
		limit 1
		""",
		{"user": user, "task": task},
		as_dict=True,
	)
	return rows[0].name if rows else None


def _get_or_create_draft_timesheet(
	user: str, employee: str, company: str, project: str | None, task: str
) -> frappe.Document:
	existing_name = _find_draft_timesheet(user, employee, project, task)
	if existing_name:
		doc = frappe.get_doc("Timesheet", existing_name)
		if not doc.employee:
			doc.employee = employee
		if not doc.company:
			doc.company = company
		if project and not doc.parent_project:
			doc.parent_project = project
		return doc

	doc = frappe.new_doc("Timesheet")
	doc.employee = employee
	doc.company = company
	doc.user = user
	if project:
		doc.parent_project = project
	return doc


def _ensure_timesheet_project(timesheet: frappe.Document, project: str | None) -> None:
	if not project:
		return
	if timesheet.parent_project and timesheet.parent_project != project:
		frappe.throw(
			_("This timesheet is for project {0}. Use a task on that project or submit the draft first.").format(
				timesheet.parent_project
			),
			title=_("Project Mismatch"),
		)
	if not timesheet.parent_project:
		timesheet.parent_project = project


def _timer_elapsed_seconds(from_time) -> int:
	if not from_time:
		return 0
	return max(0, int(flt(time_diff_in_hours(now_datetime(), get_datetime(from_time)) * 3600)))


def _timer_started_at_epoch(from_time) -> int | None:
	if not from_time:
		return None
	return int(get_datetime(from_time).timestamp())


def _set_task_working(task_name: str) -> None:
	"""When the timer is started, move Open tasks to Working (no manual status change)."""
	task = frappe.get_doc("Task", task_name)
	if task.status in LOCKED_TASK_STATUSES:
		return
	if task.status == OPEN_STATUS:
		task.status = WORKING_STATUS
		task.save(ignore_permissions=True)


def _apply_task_update(
	task_name: str,
	*,
	progress: float | None = None,
	complete: bool = False,
) -> dict:
	task = frappe.get_doc("Task", task_name)
	if complete:
		if task.status == COMPLETED_STATUS:
			return {"name": task.name, "status": task.status, "progress": flt(task.progress)}
		task.progress = 100
		task.status = COMPLETED_STATUS
		task.completed_by = frappe.session.user
		task.completed_on = today()
	else:
		if task.status in LOCKED_TASK_STATUSES:
			frappe.throw(
				_("Task status cannot be changed once {0}.").format(task.status),
				title=_("Status Locked"),
			)
		if progress is not None:
			progress = flt(progress)
			if progress < 0 or progress > 100:
				frappe.throw(_("Progress must be between 0 and 100."))
			task.progress = progress

	task.save(ignore_permissions=True)
	return {"name": task.name, "status": task.status, "progress": flt(task.progress)}


def _auto_stop_running_timer_on_other_task(user: str, new_task: str) -> dict | None:
	"""Stop an active timer on another task so a new task can be started."""
	existing = _get_running_time_log(user)
	if not existing or existing.task == new_task:
		return None

	_check_task_access(existing.task)
	timesheet = frappe.get_doc("Timesheet", existing.timesheet_name)
	result = _close_time_log_row(timesheet, existing.detail_name, submit_after=False)
	_set_timer_paused(user, existing.task, False)
	return {"stopped_task": existing.task, "stopped": result}


def _close_open_time_logs_for_task(user: str, task: str) -> None:
	rows = frappe.db.sql(
		"""
		select td.name as detail_name, td.parent as timesheet
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		where ts.docstatus = 0
			and ts.owner = %(user)s
			and td.task = %(task)s
			and td.from_time is not null
			and (td.to_time is null or td.to_time = '')
		""",
		{"user": user, "task": task},
		as_dict=True,
	)
	for row in rows:
		timesheet = frappe.get_doc("Timesheet", row.timesheet)
		_close_time_log_row(timesheet, row.detail_name, submit_after=False)


def _close_time_log_row(timesheet: frappe.Document, detail_name: str, *, submit_after: bool = False) -> dict:
	row = next((r for r in timesheet.time_logs if r.name == detail_name), None)
	if not row:
		frappe.throw(_("Active timer row not found"))

	row.to_time = now_datetime()
	# Do not set row.completed — in ERPNext that flag means "mark task complete"
	# on timesheet submit (status → Completed, progress → 100%).
	if row.from_time and row.to_time:
		row.hours = flt(time_diff_in_hours(get_datetime(row.to_time), get_datetime(row.from_time)), 3)

	timesheet.save(ignore_permissions=True)

	result = {
		"timesheet": timesheet.name,
		"detail_name": detail_name,
		"hours": row.hours,
		"from_time": row.from_time,
		"to_time": row.to_time,
		"submitted": False,
	}

	if submit_after:
		if timesheet.docstatus == 0:
			timesheet.submit()
			result["submitted"] = True

	return result


def _submit_draft_timesheet_for_task(user: str, task: str) -> dict | None:
	"""Close open rows for this task on the draft timesheet, then submit."""
	name = _find_draft_timesheet_name_for_task(user, task)
	if not name:
		return None

	timesheet = frappe.get_doc("Timesheet", name)
	changed = False
	for row in timesheet.time_logs:
		if row.task != task:
			continue
		if row.from_time and not row.to_time:
			row.to_time = now_datetime()
			if row.from_time and row.to_time:
				row.hours = flt(
					time_diff_in_hours(get_datetime(row.to_time), get_datetime(row.from_time)), 3
				)
			changed = True

	if changed:
		timesheet.save(ignore_permissions=True)

	if timesheet.docstatus != 0:
		return {"timesheet": timesheet.name, "submitted": False, "already_submitted": True}

	task_rows = [r for r in timesheet.time_logs if r.task == task and flt(r.hours) > 0]
	if not task_rows:
		return None

	timesheet.reload()
	if timesheet.docstatus == 0:
		timesheet.submit()

	return {"timesheet": timesheet.name, "submitted": True}


def get_task_timesheet_logs(task_names: list[str], user: str) -> dict[str, list[dict]]:
	if not task_names:
		return {}

	rows = frappe.db.sql(
		"""
		select
			td.task,
			td.from_time,
			td.to_time,
			td.hours,
			td.activity_type,
			ts.name as timesheet,
			ts.docstatus,
			ts.modified
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		where td.task in %(tasks)s
			and ts.owner = %(user)s
			and td.from_time is not null
		order by td.from_time desc
		""",
		{"tasks": tuple(task_names), "user": user},
		as_dict=True,
	)

	grouped: dict[str, list[dict]] = {}
	for row in rows:
		grouped.setdefault(row.task, []).append(
			{
				"timesheet": row.timesheet,
				"from_time": row.from_time,
				"to_time": row.to_time,
				"hours": flt(row.hours, 3),
				"activity_type": row.activity_type,
				"docstatus": row.docstatus,
				"status_label": _("Submitted") if row.docstatus == 1 else _("Draft"),
			}
		)
	return grouped


def enrich_tasks_with_timer(tasks: list, user: str) -> None:
	if not tasks:
		return

	task_names = [t.name for t in tasks]
	logs_by_task = get_task_timesheet_logs(task_names, user)
	running = _get_running_time_log(user)
	running_task = running.task if running else None

	for task in tasks:
		logs = logs_by_task.get(task.name, [])[:5]
		total_hours = sum(flt(log.get("hours")) for log in logs if log.get("hours"))
		task.timesheet_logs = logs
		task.total_logged_hours = flt(total_hours, 2)
		task.timer_running = task.name == running_task
		started_at = running.from_time if task.timer_running and running else None
		task.timer_started_at = started_at
		task.timer_started_at_epoch = _timer_started_at_epoch(started_at)
		task.timer_elapsed_seconds = _timer_elapsed_seconds(started_at) if task.timer_running and running else 0
		task.timer_paused = not task.timer_running and _is_timer_paused(user, task.name)
		task.timer_expected_hours = None
		if task.timer_running and running:
			task.timer_timesheet = running.timesheet_name
			task.timer_detail_name = running.detail_name
			task.timer_expected_hours = running.expected_hours
		elif not task.timer_running:
			task.timer_timesheet = None
			task.timer_detail_name = None

		if not task.timer_expected_hours:
			expected = frappe.db.get_value("Task", task.name, "expected_time")
			task.timer_expected_hours = flt(expected) if expected else None


def _timer_payload(task_name: str, running: dict | None = None) -> dict:
	running = running or _get_running_time_log(frappe.session.user, task_name)
	task = frappe.db.get_value(
		"Task",
		task_name,
		["name", "subject", "project", "expected_time", "status", "progress"],
		as_dict=True,
	)
	logs = get_task_timesheet_logs([task_name], frappe.session.user).get(task_name, [])[:5]
	total_hours = sum(flt(log.get("hours")) for log in logs if log.get("hours"))
	started_at = running.from_time if running else None

	payload = {
		"task": task_name,
		"status": task.status,
		"progress": flt(task.progress),
		"timer_running": bool(running),
		"timer_paused": not bool(running) and _is_timer_paused(frappe.session.user, task_name),
		"timer_started_at": started_at,
		"timer_started_at_epoch": _timer_started_at_epoch(started_at),
		"timer_elapsed_seconds": _timer_elapsed_seconds(started_at) if running else 0,
		"timer_expected_hours": flt(running.expected_hours if running else task.expected_time) or None,
		"timer_timesheet": running.timesheet_name if running else None,
		"timer_detail_name": running.detail_name if running else None,
		"timesheet_logs": logs,
		"total_logged_hours": flt(total_hours, 2),
	}
	return payload


@frappe.whitelist()
def start_task_timer(task: str):
	_check_task_access(task)

	user = frappe.session.user
	employee = _get_employee(user)
	if not employee:
		frappe.throw(
			_("Link your user to an Employee record before starting a task timer."),
			title=_("Employee Required"),
		)

	auto_stopped = _auto_stop_running_timer_on_other_task(user, task)

	_close_open_time_logs_for_task(user, task)
	_set_timer_paused(user, task, False)

	task_doc = frappe.get_doc("Task", task)
	company = _get_company(task, task_doc.project)
	activity_type = _get_default_activity_type()
	if not activity_type:
		frappe.throw(_("Create an Activity Type before starting a task timer."))

	timesheet = _get_or_create_draft_timesheet(user, employee, company, task_doc.project, task)
	_ensure_timesheet_project(timesheet, task_doc.project)
	_set_task_working(task)

	expected_hours = flt(task_doc.expected_time) or None
	from_time = now_datetime()
	row = timesheet.append(
		"time_logs",
		{
			"activity_type": activity_type,
			"from_time": from_time,
			"project": task_doc.project,
			"task": task,
			"expected_hours": expected_hours,
			"completed": 0,
		},
	)
	if expected_hours:
		row.to_time = None

	timesheet.save(ignore_permissions=True)
	frappe.db.commit()
	running = _get_running_time_log(user, task)
	payload = _timer_payload(task, running)
	payload["timer_started_at_epoch"] = _timer_started_at_epoch(from_time)
	payload["timer_elapsed_seconds"] = 0
	if auto_stopped:
		payload["auto_stopped_task"] = auto_stopped
	return payload


@frappe.whitelist()
def pause_task_timer(task: str):
	_check_task_access(task)
	running = _get_running_time_log(frappe.session.user, task)
	if not running:
		frappe.throw(_("No running timer for this task."))

	timesheet = frappe.get_doc("Timesheet", running.timesheet_name)
	result = _close_time_log_row(timesheet, running.detail_name, submit_after=False)
	_set_timer_paused(frappe.session.user, task, True)
	payload = _timer_payload(task)
	payload["stopped"] = result
	return payload


@frappe.whitelist()
def stop_task_timer(task: str):
	_check_task_access(task)
	user = frappe.session.user
	_set_timer_paused(user, task, False)
	running = _get_running_time_log(user, task)

	if running:
		timesheet = frappe.get_doc("Timesheet", running.timesheet_name)
		result = _close_time_log_row(timesheet, running.detail_name, submit_after=False)
		payload = _timer_payload(task)
		payload["stopped"] = result
		return payload

	return _timer_payload(task)


@frappe.whitelist()
def resume_task_timer(task: str):
	return start_task_timer(task)


@frappe.whitelist()
def get_task_timer_state(task: str):
	_check_task_access(task)
	return _timer_payload(task)


@frappe.whitelist()
def update_task_progress(task: str, progress: float):
	_check_task_access(task)
	result = _apply_task_update(task, progress=progress)
	payload = _timer_payload(task)
	payload["task_update"] = result
	return payload


@frappe.whitelist()
def complete_task(task: str):
	_check_task_access(task)
	user = frappe.session.user
	_set_timer_paused(user, task, False)

	if _get_running_time_log(user, task) or _is_timer_paused(user, task):
		frappe.throw(
			_("Stop the timer before completing this task."),
			title=_("Timer Session Active"),
		)

	timesheet_submit = _submit_draft_timesheet_for_task(user, task)
	result = _apply_task_update(task, complete=True)
	payload = _timer_payload(task)
	payload["task_update"] = result
	payload["timesheet_submit"] = timesheet_submit
	return payload
