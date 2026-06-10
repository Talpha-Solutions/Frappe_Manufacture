# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


SITE_PARENT_FIELD = "fk_parent_project"
OPEN_STATUSES = ("Open", "In Progress", "On Hold")
STATUS_COLORS = {
	"Open": "#3498db",
	"In Progress": "#2980b9",
	"Completed": "#27ae60",
	"Cancelled": "#95a5a6",
	"On Hold": "#f39c12",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	columns = get_columns(filters)
	if _resolve_site_project_filter(filters.get("site_project")):
		message = _(
			"Kitchen units for the selected site. Each row shows scheduled vs actual timelines."
		)
	else:
		message = _(
			"All sites for the company. Each row rolls up kitchen-unit dates under that site. "
			"Select a Site Project to drill into individual units."
		)
	return columns, data, message


def get_data(filters):
	filters = frappe._dict(filters or {})
	filters.site_project = _resolve_site_project_filter(filters.get("site_project"))

	if filters.site_project:
		return _get_unit_rows(filters)

	return _get_site_rows(filters)


def _get_unit_rows(filters):
	projects = _get_child_projects(filters.site_project, filters)
	if not projects:
		site = _get_site_project(filters.site_project, filters)
		projects = [site] if site else []

	if not projects:
		return []

	site = _get_site_project(filters.site_project, filters)
	data = []
	for project in sorted(projects, key=lambda row: row.name):
		row = _build_timeline_row(
			project,
			site=site,
			view_level="unit",
			filters=filters,
		)
		if row:
			data.append(row)

	return data


def _get_site_rows(filters):
	sites = _get_site_projects(filters)
	if not sites:
		return []

	data = []
	for site in sorted(sites, key=lambda row: row.name):
		children = _get_child_projects(site.name, filters)
		row = _build_site_rollup_row(site, children, filters)
		if row:
			data.append(row)

	return data


def _build_site_rollup_row(site, children, filters):
	expected_start, expected_end, actual_start, actual_end, status = _rollup_site_dates(site, children)

	if not any([actual_start, actual_end, expected_start, expected_end]):
		return None

	row = _build_timeline_row(
		site,
		site=site,
		view_level="site",
		filters=filters,
		date_overrides={
			"expected_start_date": expected_start,
			"expected_end_date": expected_end,
			"actual_start_date": actual_start,
			"actual_end_date": actual_end,
			"status": status,
		},
		unit_count=len(children),
	)
	return row


def _build_timeline_row(project, site=None, view_level="unit", filters=None, date_overrides=None, unit_count=0):
	filters = frappe._dict(filters or {})
	dates = frappe._dict(date_overrides or {})
	actual_start = dates.actual_start_date if "actual_start_date" in dates else project.actual_start_date
	actual_end = dates.actual_end_date if "actual_end_date" in dates else project.actual_end_date
	expected_start = dates.expected_start_date if "expected_start_date" in dates else project.expected_start_date
	expected_end = dates.expected_end_date if "expected_end_date" in dates else project.expected_end_date
	status = dates.status if "status" in dates else (project.status or "")

	if not any([actual_start, actual_end, expected_start, expected_end]):
		return None

	actual_chart_start, actual_chart_end = _resolve_actual_chart_dates(actual_start, actual_end, status)
	if not _project_in_date_range(
		actual_chart_start,
		actual_chart_end,
		expected_start,
		expected_end,
		filters,
	):
		return None

	if view_level == "site":
		site_ref = project
	else:
		site_ref = site

	duration_days = _duration_days(actual_chart_start, actual_chart_end)
	delay_days = _delay_days(expected_end, actual_end, status)
	schedule_status = _schedule_status(expected_end, actual_end, status)

	return {
		"view_level": view_level,
		"unit_count": unit_count,
		"site": site_ref.name if site_ref else "",
		"site_name": (site_ref.project_name or site_ref.name) if site_ref else "",
		"project": project.name,
		"project_name": project.project_name or project.name,
		"project_type": project.project_type or "",
		"status": status,
		"actual_start_date": actual_start,
		"actual_end_date": actual_end,
		"expected_start_date": expected_start,
		"expected_end_date": expected_end,
		"actual_chart_start_date": actual_chart_start,
		"actual_chart_end_date": actual_chart_end,
		"expected_chart_start_date": expected_start,
		"expected_chart_end_date": expected_end,
		"duration_days": duration_days,
		"delay_days": delay_days,
		"schedule_status": schedule_status,
		"status_color": STATUS_COLORS.get(status, "#5dade2"),
		"is_ongoing": 1 if actual_chart_start and not actual_end else 0,
		"has_scheduled_bar": 1 if expected_start and expected_end else 0,
		"has_actual_bar": 1 if actual_chart_start else 0,
	}


def _rollup_site_dates(site, children):
	timeline_children = [child for child in children if _child_has_timeline_dates(child)]
	source = timeline_children or [site]

	expected_starts = [row.expected_start_date for row in source if row.expected_start_date]
	expected_ends = [row.expected_end_date for row in source if row.expected_end_date]
	actual_starts = [row.actual_start_date for row in source if row.actual_start_date]
	actual_ends = [row.actual_end_date for row in source if row.actual_end_date]

	expected_start = min(expected_starts, key=getdate) if expected_starts else None
	expected_end = max(expected_ends, key=getdate) if expected_ends else None
	actual_start = min(actual_starts, key=getdate) if actual_starts else None

	ongoing = any(
		row.actual_start_date
		and not row.actual_end_date
		and (row.status or "") not in ("Completed", "Cancelled")
		for row in source
	)
	actual_end = None if ongoing else (max(actual_ends, key=getdate) if actual_ends else None)

	status = site.status or ""
	if ongoing and status in ("Completed", "Cancelled"):
		status = "In Progress"
	elif not ongoing and timeline_children:
		child_statuses = {(row.status or "") for row in timeline_children}
		if child_statuses == {"Completed"}:
			status = "Completed"
		elif "In Progress" in child_statuses or "Open" in child_statuses:
			status = "In Progress"

	return expected_start, expected_end, actual_start, actual_end, status


def _child_has_timeline_dates(project):
	return bool(
		project.actual_start_date
		or project.actual_end_date
		or project.expected_start_date
		or project.expected_end_date
	)


def _resolve_actual_chart_dates(actual_start, actual_end, status):
	"""Actual bar on chart — extend open projects to today."""
	if not actual_start:
		return None, None

	chart_end = actual_end
	if not chart_end and status not in ("Completed", "Cancelled"):
		chart_end = today()
	elif chart_end and getdate(chart_end) <= getdate(actual_start) and status in OPEN_STATUSES:
		chart_end = today()

	return actual_start, chart_end


def _base_project_filters(filters):
	project_filters = {
		"docstatus": ("<", 2),
		"company": filters.company,
	}
	if filters.get("status"):
		project_filters["status"] = filters.status
	return project_filters


def _get_site_projects(filters):
	return frappe.get_all(
		"Project",
		filters={**_base_project_filters(filters), "project_type": "Site"},
		fields=_project_fields(),
		order_by="name asc",
	)


def _get_site_project(site_id, filters):
	rows = frappe.get_all(
		"Project",
		filters={**_base_project_filters(filters), "name": site_id},
		fields=_project_fields(),
		limit=1,
	)
	return rows[0] if rows else None


def _get_child_projects(site_id, filters):
	if not frappe.db.has_column("Project", SITE_PARENT_FIELD):
		return []

	child_filters = {
		**_base_project_filters(filters),
		SITE_PARENT_FIELD: site_id,
		"project_type": ("!=", "Site"),
	}
	return frappe.get_all(
		"Project",
		filters=child_filters,
		fields=_project_fields(),
		order_by="name asc",
	)


def _project_fields():
	fields = [
		"name",
		"project_name",
		"project_type",
		"status",
		"actual_start_date",
		"actual_end_date",
		"expected_start_date",
		"expected_end_date",
	]
	if frappe.db.has_column("Project", SITE_PARENT_FIELD):
		fields.append(SITE_PARENT_FIELD)
	return fields


def _project_in_date_range(actual_start, actual_end, expected_start, expected_end, filters):
	if not filters.get("from_date") and not filters.get("to_date"):
		return True

	from_date = getdate(filters.from_date) if filters.get("from_date") else None
	to_date = getdate(filters.to_date) if filters.get("to_date") else None

	ranges = []
	for start, end in (
		(actual_start, actual_end),
		(expected_start, expected_end),
	):
		if not start and not end:
			continue
		range_start = getdate(start) if start else getdate(end)
		range_end = getdate(end) if end else getdate(start)
		ranges.append((range_start, range_end))

	if not ranges:
		return False

	for range_start, range_end in ranges:
		if from_date and range_end < from_date:
			continue
		if to_date and range_start > to_date:
			continue
		return True

	return False


def _duration_days(start_date, end_date):
	if not start_date or not end_date:
		return None
	return date_diff(getdate(end_date), getdate(start_date)) + 1


def _delay_days(expected_end, actual_end, status):
	if not expected_end:
		return None
	compare_end = actual_end or (today() if status not in ("Completed", "Cancelled") else None)
	if not compare_end:
		return None
	return date_diff(getdate(compare_end), getdate(expected_end))


def _schedule_status(expected_end, actual_end, status):
	if not expected_end:
		return ""
	compare_end = actual_end or (today() if status not in ("Completed", "Cancelled") else None)
	if not compare_end:
		return ""
	delay = date_diff(getdate(compare_end), getdate(expected_end))
	if delay > 0:
		return "Late"
	if delay < 0:
		return "Early"
	return "On Time"


def _resolve_site_project_filter(site_project):
	if not site_project:
		return None

	site_project = str(site_project).strip()
	if " — " in site_project:
		site_project = site_project.split(" — ", 1)[0].strip()

	paren_match = re.search(r"\(([^)]+)\)\s*$", site_project)
	if paren_match:
		site_project = paren_match.group(1).strip()

	if frappe.db.exists("Project", site_project):
		return site_project

	return frappe.db.get_value(
		"Project",
		{"project_name": site_project, "project_type": "Site"},
		"name",
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def site_project_query(doctype, txt, searchfield, start, page_len, filters):
	filters = frappe._dict(filters or {})
	like = f"%{txt or ''}%"
	site_filters = {
		"docstatus": ("<", 2),
		"project_type": "Site",
	}
	if filters.get("company"):
		site_filters["company"] = filters.company

	sites = frappe.get_all(
		"Project",
		filters=site_filters,
		or_filters={
			"name": ["like", like],
			"project_name": ["like", like],
		},
		fields=["name", "project_name"],
		order_by="name asc",
		limit_start=start,
		limit_page_length=page_len,
	)

	return [
		[row.name, _format_site_project_label(row.name, row.project_name)] for row in sites
	]


def _format_site_project_label(name, project_name):
	project_name = (project_name or "").strip()
	if project_name:
		return f"{project_name} ({name})"
	return name


def get_columns(filters):
	return [
		{
			"label": _("Site"),
			"fieldname": "site",
			"fieldtype": "Link",
			"options": "Project",
			"width": 110,
		},
		{
			"label": _("Site Name"),
			"fieldname": "site_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 110,
		},
		{
			"label": _("Project Name"),
			"fieldname": "project_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Type"),
			"fieldname": "project_type",
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Actual Start Date"),
			"fieldname": "actual_start_date",
			"fieldtype": "Date",
			"width": 130,
		},
		{
			"label": _("Actual End Date"),
			"fieldname": "actual_end_date",
			"fieldtype": "Date",
			"width": 130,
		},
		{
			"label": _("Expected Start Date"),
			"fieldname": "expected_start_date",
			"fieldtype": "Date",
			"width": 140,
		},
		{
			"label": _("Expected End Date"),
			"fieldname": "expected_end_date",
			"fieldtype": "Date",
			"width": 140,
		},
		{
			"label": _("Duration (Days)"),
			"fieldname": "duration_days",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": _("Schedule"),
			"fieldname": "schedule_status",
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"label": _("Delay (Days)"),
			"fieldname": "delay_days",
			"fieldtype": "Int",
			"width": 100,
		},
	]
