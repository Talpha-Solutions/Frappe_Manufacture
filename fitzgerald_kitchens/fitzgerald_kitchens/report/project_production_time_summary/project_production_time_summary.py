# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	data = get_data(filters)
	columns = get_columns()
	chart = get_chart_data(data)
	return columns, data, None, chart


def get_data(filters):
	project_filters = {
		"docstatus": ("<", 2),
		"company": filters.company,
	}

	if filters.get("project"):
		project_filters["name"] = filters.project

	projects = frappe.get_all(
		"Project",
		filters=project_filters,
		fields=["name", "project_name", "project_template", "expected_start_date", "creation"],
	)

	if not projects:
		return []

	projects = _filter_projects_by_date(projects, filters)
	if not projects:
		return []

	project_names = [row.name for row in projects]
	work_order_metrics = _get_work_order_metrics(project_names, filters)
	task_metrics = _get_task_metrics(project_names, filters)

	data = []
	for project in sorted(projects, key=lambda row: row.name):
		wo = work_order_metrics.get(project.name, {})
		task = task_metrics.get(project.name, {})

		scheduled_time = flt(wo.get("scheduled_time"))
		actual_time = flt(wo.get("actual_time"))
		task_scheduled_time = flt(task.get("task_scheduled_time"))
		task_actual_time = flt(task.get("task_actual_time"))

		if not any(
			[
				wo.get("work_order_count"),
				task.get("timesheet_task_count"),
				task_scheduled_time,
				task_actual_time,
				scheduled_time,
				actual_time,
			]
		):
			continue

		if filters.get("status") and wo.get("work_order_count") and not wo.get("matches_status"):
			if not task.get("timesheet_task_count") and not task_scheduled_time:
				continue

		data.append(
			{
				"project": project.name,
				"project_name": project.project_name or project.name,
				"work_order_count": wo.get("work_order_count", 0),
				"job_card_count": wo.get("job_card_count", 0),
				"scheduled_time": scheduled_time,
				"actual_time": actual_time,
				"extra_time": actual_time - scheduled_time,
				"timesheet_task_count": task.get("timesheet_task_count", 0),
				"task_scheduled_time": task_scheduled_time,
				"task_actual_time": task_actual_time,
				"task_extra_time": task_actual_time - task_scheduled_time,
			}
		)

	return data


def _filter_projects_by_date(projects, filters):
	from_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)
	filtered = []

	for project in projects:
		reference_date = getdate(project.expected_start_date or project.creation)
		if from_date <= reference_date <= to_date:
			filtered.append(project)

	return filtered


def _get_work_order_metrics(project_names, filters):
	work_order_filters = {
		"docstatus": ("<", 2),
		"project": ("in", project_names),
	}

	if filters.get("status"):
		work_order_filters["status"] = filters.status

	work_orders = frappe.get_all(
		"Work Order",
		filters=work_order_filters,
		fields=["name", "project", "planned_start_date", "creation", "status"],
	)

	work_orders = _filter_work_orders_by_date(work_orders, filters)
	if not work_orders:
		return {}

	work_order_names = [row.name for row in work_orders]
	scheduled_times = _get_work_order_scheduled_times(work_order_names)
	actual_times = _get_work_order_actual_times(work_order_names)
	job_card_counts = _get_job_card_counts(work_order_names)

	metrics = defaultdict(
		lambda: {
			"scheduled_time": 0.0,
			"actual_time": 0.0,
			"work_order_count": 0,
			"job_card_count": 0,
			"matches_status": False,
		}
	)

	for work_order in work_orders:
		row = metrics[work_order.project]
		row["work_order_count"] += 1
		row["matches_status"] = True
		row["scheduled_time"] += scheduled_times.get(work_order.name, 0)
		row["actual_time"] += actual_times.get(work_order.name, 0)
		row["job_card_count"] += job_card_counts.get(work_order.name, 0)

	return dict(metrics)


def _filter_work_orders_by_date(work_orders, filters):
	from_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)
	filtered = []

	for work_order in work_orders:
		reference_date = getdate(work_order.planned_start_date or work_order.creation)
		if from_date <= reference_date <= to_date:
			filtered.append(work_order)

	return filtered


def _get_task_metrics(project_names, filters):
	project_templates = {
		row.name: row.project_template
		for row in frappe.get_all(
			"Project",
			filters={"name": ("in", project_names)},
			fields=["name", "project_template"],
		)
	}

	template_scheduled_hours = _get_template_scheduled_hours(set(project_templates.values()))
	timesheet_metrics = _get_timesheet_metrics(project_names, filters)

	metrics = {}
	for project in project_names:
		template = project_templates.get(project)
		task_scheduled_time = template_scheduled_hours.get(template, 0) if template else 0
		timesheet = timesheet_metrics.get(project, {})

		metrics[project] = {
			"timesheet_task_count": timesheet.get("timesheet_task_count", 0),
			"task_scheduled_time": task_scheduled_time,
			"task_actual_time": timesheet.get("task_actual_time", 0),
		}

	return metrics


def _get_template_scheduled_hours(template_names):
	template_names = [name for name in template_names if name]
	if not template_names:
		return {}

	scheduled_hours = {}
	for row in frappe.db.sql(
		"""
		select
			ptt.parent as project_template,
			sum(coalesce(task.expected_time, 0)) as scheduled_hours
		from `tabProject Template Task` ptt
		inner join `tabTask` task on task.name = ptt.task
		where ptt.parent in %(templates)s
		group by ptt.parent
		""",
		{"templates": template_names},
		as_dict=True,
	):
		scheduled_hours[row.project_template] = flt(row.scheduled_hours)

	return scheduled_hours


def _get_timesheet_metrics(project_names, filters):
	from_date = filters.from_date
	to_date = filters.to_date

	rows = frappe.db.sql(
		"""
		select
			td.project as project,
			count(distinct td.task) as timesheet_task_count,
			sum(coalesce(td.hours, 0)) as task_actual_time
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		where ts.docstatus = 1
			and td.project in %(projects)s
			and td.task is not null
			and td.task != ''
			and coalesce(date(td.from_time), ts.start_date) between %(from_date)s and %(to_date)s
		group by td.project
		""",
		{"projects": project_names, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)

	return {
		row.project: {
			"timesheet_task_count": row.timesheet_task_count,
			"task_actual_time": flt(row.task_actual_time),
		}
		for row in rows
	}


def _get_work_order_scheduled_times(work_order_names):
	scheduled_times = {}
	for row in frappe.get_all(
		"Work Order Operation",
		filters={"parent": ("in", work_order_names)},
		fields=["parent", {"SUM": "time_in_mins", "as": "scheduled_time"}],
		group_by="parent",
	):
		scheduled_times[row.parent] = flt(row.scheduled_time)
	return scheduled_times


def _get_work_order_actual_times(work_order_names):
	job_cards = frappe.get_all(
		"Job Card",
		filters={"work_order": ("in", work_order_names), "docstatus": ("<", 2)},
		fields=["name", "work_order", "total_time_in_mins"],
	)

	if not job_cards:
		return {}

	job_card_names = [row.name for row in job_cards]
	actual_by_job_card = _get_job_card_actual_times(job_card_names)

	actual_by_work_order = defaultdict(float)
	for job_card in job_cards:
		if job_card.name in actual_by_job_card:
			actual_by_work_order[job_card.work_order] += actual_by_job_card[job_card.name]
		else:
			actual_by_work_order[job_card.work_order] += flt(job_card.total_time_in_mins)

	return dict(actual_by_work_order)


def _get_job_card_counts(work_order_names):
	counts = {}
	for row in frappe.get_all(
		"Job Card",
		filters={"work_order": ("in", work_order_names), "docstatus": ("<", 2)},
		fields=["work_order", {"COUNT": "name", "as": "job_card_count"}],
		group_by="work_order",
	):
		counts[row.work_order] = row.job_card_count
	return counts


def _get_job_card_actual_times(job_card_names):
	actual_times = {}
	for row in frappe.get_all(
		"Job Card Time Log",
		filters={"parent": ("in", job_card_names), "docstatus": ("<", 2)},
		fields=["parent", {"SUM": "time_in_mins", "as": "actual_time"}],
		group_by="parent",
	):
		actual_times[row.parent] = flt(row.actual_time)
	return actual_times


def get_chart_data(data):
	if not data:
		return None

	labels = [row.get("project_name") or row.get("project") for row in data]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Manufacturing Scheduled (Hrs)"),
					"values": [flt(flt(row.get("scheduled_time")) / 60, 2) for row in data],
				},
				{
					"name": _("Manufacturing Actual (Hrs)"),
					"values": [flt(flt(row.get("actual_time")) / 60, 2) for row in data],
				},
				{
					"name": _("Task Scheduled (Hrs)"),
					"values": [flt(row.get("task_scheduled_time"), 2) for row in data],
				},
				{
					"name": _("Task Actual (Hrs)"),
					"values": [flt(row.get("task_actual_time"), 2) for row in data],
				},
			],
		},
		"type": "bar",
	}


def get_columns():
	return [
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{
			"label": _("Project Name"),
			"fieldname": "project_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Work Orders"),
			"fieldname": "work_order_count",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Job Cards"),
			"fieldname": "job_card_count",
			"fieldtype": "Int",
			"width": 90,
		},
		{
			"label": _("Manufacturing Scheduled (In Mins)"),
			"fieldname": "scheduled_time",
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"label": _("Manufacturing Actual (In Mins)"),
			"fieldname": "actual_time",
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"label": _("Manufacturing Extra (In Mins)"),
			"fieldname": "extra_time",
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"label": _("Timesheet Tasks"),
			"fieldname": "timesheet_task_count",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": _("Task Scheduled (In Hrs)"),
			"fieldname": "task_scheduled_time",
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"label": _("Task Actual (In Hrs)"),
			"fieldname": "task_actual_time",
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"label": _("Task Extra (In Hrs)"),
			"fieldname": "task_extra_time",
			"fieldtype": "Float",
			"width": 130,
		},
	]
