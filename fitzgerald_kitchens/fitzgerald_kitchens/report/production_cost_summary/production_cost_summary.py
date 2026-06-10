# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

from fitzgerald_kitchens.fitzgerald_kitchens.utils.project_manufacturing_cost import (
	get_task_metrics,
	get_work_order_metrics,
)


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
	work_order_metrics = get_work_order_metrics(
		project_names,
		filters.from_date,
		filters.to_date,
		status=filters.get("status") or None,
	)
	task_metrics = get_task_metrics(project_names, filters.from_date, filters.to_date)

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
