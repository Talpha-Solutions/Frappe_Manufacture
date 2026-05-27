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
	work_order_filters = {
		"docstatus": ("<", 2),
		"company": filters.company,
		"project": ("is", "set"),
	}

	if filters.get("project"):
		work_order_filters["project"] = filters.project

	if filters.get("status"):
		work_order_filters["status"] = filters.status

	work_orders = frappe.get_all(
		"Work Order",
		filters=work_order_filters,
		fields=["name", "project", "planned_start_date", "creation"],
	)

	if not work_orders:
		return []

	work_order_names = [row.name for row in work_orders]
	work_orders = _filter_work_orders_by_date(work_orders, filters)
	if not work_orders:
		return []

	work_order_names = [row.name for row in work_orders]
	scheduled_times = _get_work_order_scheduled_times(work_order_names)
	actual_times = _get_work_order_actual_times(work_order_names)
	job_card_counts = _get_job_card_counts(work_order_names)

	project_rows = defaultdict(
		lambda: {
			"scheduled_time": 0.0,
			"actual_time": 0.0,
			"work_order_count": 0,
			"job_card_count": 0,
		}
	)

	for work_order in work_orders:
		project = work_order.project
		if not project:
			continue

		row = project_rows[project]
		row["work_order_count"] += 1
		row["scheduled_time"] += scheduled_times.get(work_order.name, 0)
		row["actual_time"] += actual_times.get(work_order.name, 0)
		row["job_card_count"] += job_card_counts.get(work_order.name, 0)

	project_names = {
		row.name: row.project_name
		for row in frappe.get_all(
			"Project",
			filters={"name": ("in", list(project_rows.keys()))},
			fields=["name", "project_name"],
		)
	}

	data = []
	for project, values in sorted(project_rows.items(), key=lambda item: item[0]):
		scheduled_time = flt(values["scheduled_time"])
		actual_time = flt(values["actual_time"])
		data.append(
			{
				"project": project,
				"project_name": project_names.get(project) or project,
				"work_order_count": values["work_order_count"],
				"job_card_count": values["job_card_count"],
				"scheduled_time": scheduled_time,
				"actual_time": actual_time,
				"extra_time": actual_time - scheduled_time,
			}
		)

	return data


def _filter_work_orders_by_date(work_orders, filters):
	from_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)
	filtered = []

	for work_order in work_orders:
		reference_date = getdate(work_order.planned_start_date or work_order.creation)
		if from_date <= reference_date <= to_date:
			filtered.append(work_order)

	return filtered


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
	actual_by_job_card = _get_actual_times(job_card_names)

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


def _get_actual_times(job_card_names):
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
	scheduled_time = [row.get("scheduled_time") for row in data]
	actual_time = [row.get("actual_time") for row in data]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Scheduled Time (In Mins)"), "values": scheduled_time},
				{"name": _("Actual Time (In Mins)"), "values": actual_time},
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
			"width": 140,
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
			"width": 110,
		},
		{
			"label": _("Job Cards"),
			"fieldname": "job_card_count",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Scheduled Time (In Mins)"),
			"fieldname": "scheduled_time",
			"fieldtype": "Float",
			"width": 150,
		},
		{
			"label": _("Actual Time (In Mins)"),
			"fieldname": "actual_time",
			"fieldtype": "Float",
			"width": 150,
		},
		{
			"label": _("Extra Time (In Mins)"),
			"fieldname": "extra_time",
			"fieldtype": "Float",
			"width": 150,
		},
	]
