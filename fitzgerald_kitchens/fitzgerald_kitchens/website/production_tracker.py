# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Production stage tracker data for the /project portal page."""

from __future__ import annotations

import json
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from fitzgerald_kitchens.www.project_photos import (
	_detect_category,
	_get_project_type_label,
	_normalize_task_type,
)

PRODUCTION_STAGES = (
	"Survey",
	"Drawing",
	"Export",
	"Manufacturing",
	"Assembly",
	"Despatch",
	"Delivery",
	"Fitting",
	"Handover",
)

STAGE_COUNT = len(PRODUCTION_STAGES)

EXCLUDED_TASK_STATUSES = frozenset({"Cancelled", "Template"})

EXCLUDED_PROJECT_TYPES = frozenset({"Site"})

IN_PROGRESS_TASK_STATUSES = frozenset({"Open", "Working", "Pending Review", "Overdue"})

FILTER_BUTTONS = [
	{"key": "all", "label": _("All units")},
	{"key": "kitchens", "label": _("Kitchens")},
	{"key": "wardrobes", "label": _("Wardrobes")},
	{"key": "utilities", "label": _("Utilities")},
	{"key": "vanity", "label": _("Vanity unit")},
	{"key": "pantry", "label": _("Pantry")},
	{"key": "attention", "label": _("Needs attention")},
]

LEGEND_ITEMS = [
	{"state": "on_time", "label": _("Completed on time")},
	{"state": "late", "label": _("Completed late")},
	{"state": "due_today", "label": _("Due today")},
	{"state": "overdue", "label": _("Overdue")},
	{"state": "not_started", "label": _("Not yet started")},
]


def get_tracker_context(focused_project: str | None = None) -> dict:
	"""Build template context for the production stage tracker page."""
	focused = _resolve_focused_project(focused_project)
	projects = _get_active_projects()
	projects = _ensure_focused_project_in_list(projects, focused)
	project_names = [row.name for row in projects]
	tasks = _get_tasks_for_projects(project_names)
	tasks_by_project = _group_tasks_by_project(tasks)

	user_names = _collect_user_ids(tasks)
	user_map = _get_user_map(user_names)

	tracker_projects = []
	global_metrics = _new_global_metrics()

	for project in projects:
		project_tasks = tasks_by_project.get(project.name, [])
		stage_tasks = _map_stage_tasks(project_tasks)
		stages = [_build_stage_cell(stage_name, stage_tasks.get(stage_name), user_map) for stage_name in PRODUCTION_STAGES]

		_accumulate_global_metrics(global_metrics, project_tasks)

		completed_count = sum(1 for stage in stages if stage.get("status") == "Completed")
		progress_percent = int(round((completed_count / STAGE_COUNT) * 100)) if STAGE_COUNT else 0

		project_type = _get_project_type_label(project)
		project_name = (project.get("project_name") or project.name).strip()

		tracker_projects.append(
			{
				"name": project.name,
				"project_name": project_name,
				"project_type": project_type,
				"display_title": _format_display_title(project_name, project_type),
				"location": (project.get("customer") or "").strip(),
				"category": _detect_category(project_type),
				"search_text": _build_search_text(project_name, project_type, project.name),
				"tasks_completed": completed_count,
				"tasks_total": STAGE_COUNT,
				"progress_percent": progress_percent,
				"needs_attention": any(stage["state"] in ("overdue", "due_today") for stage in stages),
				"stages": stages,
				"detail_url": f"/projects?project={quote(project.name)}",
			}
		)

	on_time_rate = 0
	if global_metrics["due_or_completed_denominator"]:
		on_time_rate = int(
			round(
				(global_metrics["completed_on_time"] / global_metrics["due_or_completed_denominator"]) * 100
			)
		)

	return {
		"page_title": _("Production stage tracker"),
		"today_label": getdate(today()).strftime("%a %d %b %Y"),
		"legend_items": LEGEND_ITEMS,
		"filter_buttons": FILTER_BUTTONS,
		"kpi": {
			"units_in_production": len(projects),
			"tasks_overdue": global_metrics["overdue"],
			"due_today": global_metrics["due_today"],
			"on_time_rate": on_time_rate,
		},
		"projects": tracker_projects,
		"no_result_message": _("No projects found."),
		"focused_project": focused.get("name") if focused else None,
		"initial_search": focused.get("initial_search", "") if focused else "",
	}


def _resolve_focused_project(project_id: str | None) -> dict | None:
	if not project_id:
		return None

	project_id = str(project_id).strip()
	if not project_id or not frappe.db.exists("Project", project_id):
		return None

	try:
		project = frappe.get_doc("Project", project_id)
		project.has_permission("read")
	except frappe.PermissionError:
		return None

	project_type = _get_project_type_label(project)
	project_name = (project.project_name or project.name).strip()

	return {
		"name": project.name,
		"project_name": project_name,
		"initial_search": project_name or project.name,
	}


def _project_list_fields() -> list[str]:
	fields = ["name", "project_name", "status", "customer"]
	if frappe.get_meta("Project").has_field("project_type"):
		fields.append("project_type")
	return fields


def _get_active_projects():
	fields = _project_list_fields()
	filters = {"status": ["not in", ["Cancelled", "Completed"]]}
	if "project_type" in fields:
		filters["project_type"] = ["not in", list(EXCLUDED_PROJECT_TYPES)]

	try:
		return frappe.get_list(
			"Project",
			fields=fields,
			filters=filters,
			order_by="creation asc",
			limit_page_length=500,
		)
	except frappe.PermissionError:
		return []


def _get_project_list_row(project_id: str):
	rows = frappe.get_list(
		"Project",
		fields=_project_list_fields(),
		filters={"name": project_id},
		limit_page_length=1,
	)
	return rows[0] if rows else None


def _ensure_focused_project_in_list(projects, focused: dict | None):
	if not focused:
		return projects

	project_names = {row.name for row in projects}
	if focused["name"] in project_names:
		return projects

	focused_row = _get_project_list_row(focused["name"])
	if not focused_row:
		return projects

	return [*projects, focused_row]


def _get_tasks_for_projects(project_names: list[str]):
	if not project_names:
		return []

	fields = [
		"name",
		"subject",
		"project",
		"type",
		"status",
		"exp_start_date",
		"exp_end_date",
		"completed_on",
		"completed_by",
		"_assign",
		"progress",
		"creation",
		"modified",
		"idx",
	]

	return frappe.get_list(
		"Task",
		filters={
			"project": ["in", project_names],
			"status": ["not in", list(EXCLUDED_TASK_STATUSES)],
		},
		fields=fields,
		order_by="creation asc, idx asc",
		limit_page_length=5000,
	)


def _group_tasks_by_project(tasks):
	grouped = {}
	for task in tasks or []:
		grouped.setdefault(task.project, []).append(task)
	return grouped


def _task_is_newer(task, existing) -> bool:
	task_key = (task.get("modified") or task.get("creation"), task.get("idx") or 0)
	existing_key = (existing.get("modified") or existing.get("creation"), existing.get("idx") or 0)
	return task_key >= existing_key


def _map_stage_tasks(project_tasks):
	"""Pick the best task row per production stage (latest non-cancelled match)."""
	stage_tasks = {}
	for task in project_tasks or []:
		stage_name = _normalize_task_type(task.get("type"))
		if stage_name not in PRODUCTION_STAGES:
			continue
		existing = stage_tasks.get(stage_name)
		if not existing or _task_is_newer(task, existing):
			stage_tasks[stage_name] = task
	return stage_tasks


def _build_stage_cell(stage_name: str, task, user_map: dict) -> dict:
	state = get_stage_state(task)
	employee = _resolve_task_employee(task, user_map)

	display_date = "—"
	if task:
		if task.get("status") == "Completed" and task.get("completed_on"):
			display_date = formatdate(task.completed_on, "d MMM")
		elif task.get("exp_end_date"):
			display_date = formatdate(task.exp_end_date, "d MMM")

	return {
		"stage": stage_name,
		"state": state,
		"display_date": display_date,
		"employee_name": employee.get("full_name") or "",
		"employee_user": employee.get("user") or "",
		"task_name": task.name if task else "",
		"status": task.status if task else "",
		"exp_end_date": str(task.exp_end_date) if task and task.get("exp_end_date") else "",
		"exp_start_date": str(task.exp_start_date) if task and task.get("exp_start_date") else "",
		"completed_on": str(task.completed_on) if task and task.get("completed_on") else "",
		"completed_on_time": _is_completed_on_time(task) if task else None,
		"is_overdue": state == "overdue",
		"is_due_today": state == "due_today",
	}


def get_stage_state(task) -> str:
	"""Return visual state key for a timeline stage cell."""
	if not task:
		return "not_started"

	status = task.get("status")
	today_date = getdate(today())
	exp_end = task.get("exp_end_date")
	exp_start = task.get("exp_start_date")
	completed_on = task.get("completed_on")
	progress = float(task.get("progress") or 0)

	if status == "Completed":
		if exp_end and completed_on:
			if getdate(completed_on) <= getdate(exp_end):
				return "on_time"
			return "late"
		if exp_end and today_date <= getdate(exp_end):
			return "on_time"
		return "late"

	if status == "Overdue":
		return "overdue"

	if exp_end:
		expected_end = getdate(exp_end)
		if today_date > expected_end and status in IN_PROGRESS_TASK_STATUSES:
			return "overdue"
		if today_date == expected_end and status not in ("Completed", "Cancelled"):
			return "due_today"

	if status == "Template":
		return "not_started"

	if status == "Open":
		if progress == 0:
			if exp_start and today_date < getdate(exp_start):
				return "not_started"
			if not exp_start:
				return "not_started"

	return "not_started"


def task_counts_as_overdue(task) -> bool:
	if not task:
		return False
	if task.get("status") == "Overdue":
		return True
	if task.get("status") not in IN_PROGRESS_TASK_STATUSES:
		return False
	exp_end = task.get("exp_end_date")
	return bool(exp_end and getdate(today()) > getdate(exp_end))


def task_counts_as_due_today(task) -> bool:
	if not task:
		return False
	if task.get("status") in ("Completed", "Cancelled"):
		return False
	exp_end = task.get("exp_end_date")
	return bool(exp_end and getdate(today()) == getdate(exp_end))


def _is_completed_on_time(task) -> bool | None:
	if not task or task.get("status") != "Completed":
		return None
	exp_end = task.get("exp_end_date")
	completed_on = task.get("completed_on")
	if exp_end and completed_on:
		return getdate(completed_on) <= getdate(exp_end)
	if exp_end:
		return getdate(today()) <= getdate(exp_end)
	return True


def _task_counts_for_global_metrics(task) -> bool:
	"""Tasks included in overdue / due-today / on-time KPI calculations."""
	return bool(task) and task.get("status") not in EXCLUDED_TASK_STATUSES


def _new_global_metrics():
	return {
		"overdue": 0,
		"due_today": 0,
		"completed_on_time": 0,
		"due_or_completed_denominator": 0,
	}


def _accumulate_global_metrics(metrics: dict, project_tasks: list) -> None:
	seen_tasks = set()

	for task in project_tasks or []:
		if not _task_counts_for_global_metrics(task):
			continue
		if task.name in seen_tasks:
			continue
		seen_tasks.add(task.name)

		if task_counts_as_overdue(task):
			metrics["overdue"] += 1
		if task_counts_as_due_today(task):
			metrics["due_today"] += 1

		if _counts_toward_on_time_denominator(task):
			metrics["due_or_completed_denominator"] += 1
			if task.get("status") == "Completed" and _is_completed_on_time(task):
				metrics["completed_on_time"] += 1


def _counts_toward_on_time_denominator(task) -> bool:
	if task.get("status") == "Completed":
		return True
	exp_end = task.get("exp_end_date")
	return bool(exp_end and getdate(today()) >= getdate(exp_end))


def _resolve_task_employee(task, user_map: dict) -> dict:
	if not task:
		return {}

	if task.get("status") == "Completed" and task.get("completed_by"):
		user = task.completed_by
		return {"user": user, "full_name": user_map.get(user, user)}

	assignees = _parse_assignees(task.get("_assign"))
	for user in assignees:
		return {"user": user, "full_name": user_map.get(user, user)}

	return {}


def _parse_assignees(raw_assign) -> list[str]:
	if not raw_assign:
		return []
	try:
		assignees = json.loads(raw_assign)
	except (TypeError, ValueError):
		return []
	return [user for user in assignees if user]


def _collect_user_ids(tasks) -> set[str]:
	user_ids = set()
	for task in tasks or []:
		if task.get("completed_by"):
			user_ids.add(task.completed_by)
		user_ids.update(_parse_assignees(task.get("_assign")))
	return user_ids


def _get_user_map(user_ids: set[str]) -> dict[str, str]:
	if not user_ids:
		return {}

	rows = frappe.get_all(
		"User",
		filters={"name": ["in", list(user_ids)]},
		fields=["name", "full_name"],
	)
	return {row.name: row.full_name or row.name for row in rows}


def _format_display_title(project_name: str, project_type: str) -> str:
	if project_type:
		return f"{project_name} — {project_type}"
	return project_name


def _build_search_text(project_name: str, project_type: str, project_id: str = "") -> str:
	parts = [project_name, project_type, project_id]
	return " ".join(part.lower() for part in parts if part)
