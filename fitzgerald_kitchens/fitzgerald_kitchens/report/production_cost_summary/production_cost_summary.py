# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	data = get_data(filters)
	columns = get_columns(filters)
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
		fields=["name", "project_name", "estimated_costing", "expected_start_date", "creation"],
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

		scheduled_cost = flt(wo.get("scheduled_cost"), 2)
		actual_cost = flt(wo.get("actual_cost"), 2)
		task_scheduled_cost = flt(task.get("task_scheduled_cost"), 2)
		task_actual_cost = flt(task.get("task_actual_cost"), 2)

		if not any(
			[
				wo.get("work_order_count"),
				task.get("timesheet_task_count"),
				task_scheduled_cost,
				task_actual_cost,
				scheduled_cost,
				actual_cost,
			]
		):
			continue

		if filters.get("status") and wo.get("work_order_count") and not wo.get("matches_status"):
			if not task.get("timesheet_task_count") and not task_scheduled_cost:
				continue

		data.append(
			{
				"project": project.name,
				"project_name": project.project_name or project.name,
				"work_order_count": wo.get("work_order_count", 0),
				"job_card_count": wo.get("job_card_count", 0),
				"scheduled_cost": scheduled_cost,
				"actual_cost": actual_cost,
				"extra_cost": flt(actual_cost - scheduled_cost, 2),
				"timesheet_task_count": task.get("timesheet_task_count", 0),
				"task_scheduled_cost": task_scheduled_cost,
				"task_actual_cost": task_actual_cost,
				"task_extra_cost": flt(task_actual_cost - task_scheduled_cost, 2),
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
		fields=["name", "project", "planned_start_date", "creation", "planned_operating_cost"],
	)

	work_orders = _filter_work_orders_by_date(work_orders, filters)
	if not work_orders:
		return {}

	work_order_names = [row.name for row in work_orders]
	actual_costs = _get_work_order_actual_costs(work_order_names)
	job_card_counts = _get_job_card_counts(work_order_names)

	metrics = defaultdict(
		lambda: {
			"scheduled_cost": 0.0,
			"actual_cost": 0.0,
			"work_order_count": 0,
			"job_card_count": 0,
			"matches_status": False,
		}
	)

	for work_order in work_orders:
		row = metrics[work_order.project]
		row["work_order_count"] += 1
		row["matches_status"] = True
		row["scheduled_cost"] += flt(work_order.planned_operating_cost)
		row["actual_cost"] += actual_costs.get(work_order.name, 0)
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
	project_costs = {
		row.name: flt(row.estimated_costing)
		for row in frappe.get_all(
			"Project",
			filters={"name": ("in", project_names)},
			fields=["name", "estimated_costing"],
		)
	}
	timesheet_metrics = _get_timesheet_cost_metrics(project_names, filters)

	metrics = {}
	for project in project_names:
		timesheet = timesheet_metrics.get(project, {})
		metrics[project] = {
			"timesheet_task_count": timesheet.get("timesheet_task_count", 0),
			"task_scheduled_cost": project_costs.get(project, 0),
			"task_actual_cost": timesheet.get("task_actual_cost", 0),
		}

	return metrics


def _get_timesheet_cost_metrics(project_names, filters):
	rows = frappe.db.sql(
		"""
		select
			td.project as project,
			count(distinct td.task) as timesheet_task_count,
			sum(coalesce(td.base_costing_amount, td.costing_amount, 0)) as task_actual_cost
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		where ts.docstatus = 1
			and td.project in %(projects)s
			and td.task is not null
			and td.task != ''
			and coalesce(date(td.from_time), ts.start_date) between %(from_date)s and %(to_date)s
		group by td.project
		""",
		{"projects": project_names, "from_date": filters.from_date, "to_date": filters.to_date},
		as_dict=True,
	)

	return {
		row.project: {
			"timesheet_task_count": row.timesheet_task_count,
			"task_actual_cost": flt(row.task_actual_cost),
		}
		for row in rows
	}


def _get_work_order_actual_costs(work_order_names):
	job_cards = frappe.get_all(
		"Job Card",
		filters={"work_order": ("in", work_order_names), "docstatus": ("<", 2)},
		fields=["name", "work_order", "hour_rate", "total_time_in_mins"],
	)

	if not job_cards:
		return {}

	job_card_names = [row.name for row in job_cards]
	actual_times = _get_job_card_actual_times(job_card_names)

	actual_costs = defaultdict(float)
	for job_card in job_cards:
		actual_mins = actual_times.get(job_card.name, flt(job_card.total_time_in_mins))
		actual_costs[job_card.work_order] += (flt(actual_mins) / 60) * flt(job_card.hour_rate)

	return dict(actual_costs)


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
					"name": _("Manufacturing Scheduled Cost"),
					"values": [flt(row.get("scheduled_cost"), 2) for row in data],
				},
				{
					"name": _("Manufacturing Actual Cost"),
					"values": [flt(row.get("actual_cost"), 2) for row in data],
				},
				{
					"name": _("Task Scheduled Cost"),
					"values": [flt(row.get("task_scheduled_cost"), 2) for row in data],
				},
				{
					"name": _("Task Actual Cost"),
					"values": [flt(row.get("task_actual_cost"), 2) for row in data],
				},
			],
		},
		"type": "bar",
	}


def get_columns(filters):
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

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
			"label": _("Manufacturing Scheduled Cost"),
			"fieldname": "scheduled_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 160,
		},
		{
			"label": _("Manufacturing Actual Cost"),
			"fieldname": "actual_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 160,
		},
		{
			"label": _("Manufacturing Extra Cost"),
			"fieldname": "extra_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 160,
		},
		{
			"label": _("Timesheet Tasks"),
			"fieldname": "timesheet_task_count",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": _("Task Scheduled Cost"),
			"fieldname": "task_scheduled_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Task Actual Cost"),
			"fieldname": "task_actual_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
		{
			"label": _("Task Extra Cost"),
			"fieldname": "task_extra_cost",
			"fieldtype": "Currency",
			"options": currency,
			"width": 150,
		},
	]
