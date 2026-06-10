# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe.utils import flt, getdate


def get_manufacturing_actual_cost_by_project(
	project_names,
	from_date,
	to_date,
	status=None,
):
	"""Return Job Card labour actual cost per project (date-filtered work orders)."""
	if not project_names:
		return {}

	work_order_filters = {
		"docstatus": ("<", 2),
		"project": ("in", project_names),
	}
	if status:
		work_order_filters["status"] = status

	work_orders = frappe.get_all(
		"Work Order",
		filters=work_order_filters,
		fields=["name", "project", "planned_start_date", "creation"],
	)
	work_orders = filter_work_orders_by_date(work_orders, from_date, to_date)
	if not work_orders:
		return {}

	work_order_names = [row.name for row in work_orders]
	actual_costs = get_work_order_actual_costs(work_order_names)

	metrics = defaultdict(float)
	for work_order in work_orders:
		metrics[work_order.project] += actual_costs.get(work_order.name, 0)

	return dict(metrics)


def get_work_order_metrics(project_names, from_date, to_date, status=None):
	"""Scheduled and actual manufacturing cost per project (Production Cost Summary)."""
	if not project_names:
		return {}

	work_order_filters = {
		"docstatus": ("<", 2),
		"project": ("in", project_names),
	}
	if status:
		work_order_filters["status"] = status

	work_orders = frappe.get_all(
		"Work Order",
		filters=work_order_filters,
		fields=[
			"name",
			"project",
			"planned_start_date",
			"creation",
			"planned_operating_cost",
		],
	)
	work_orders = filter_work_orders_by_date(work_orders, from_date, to_date)
	if not work_orders:
		return {}

	work_order_names = [row.name for row in work_orders]
	actual_costs = get_work_order_actual_costs(work_order_names)
	job_card_counts = get_job_card_counts(work_order_names)

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


def filter_work_orders_by_date(work_orders, from_date, to_date):
	from_date = getdate(from_date)
	to_date = getdate(to_date)
	filtered = []

	for work_order in work_orders:
		reference_date = getdate(work_order.planned_start_date or work_order.creation)
		if from_date <= reference_date <= to_date:
			filtered.append(work_order)

	return filtered


def get_work_order_actual_costs(work_order_names):
	job_cards = frappe.get_all(
		"Job Card",
		filters={"work_order": ("in", work_order_names), "docstatus": ("<", 2)},
		fields=["name", "work_order", "hour_rate", "total_time_in_mins"],
	)

	if not job_cards:
		return {}

	job_card_names = [row.name for row in job_cards]
	actual_times = get_job_card_actual_times(job_card_names)

	actual_costs = defaultdict(float)
	for job_card in job_cards:
		actual_mins = actual_times.get(job_card.name, flt(job_card.total_time_in_mins))
		actual_costs[job_card.work_order] += (flt(actual_mins) / 60) * flt(job_card.hour_rate)

	return dict(actual_costs)


def get_job_card_counts(work_order_names):
	counts = {}
	for row in frappe.get_all(
		"Job Card",
		filters={"work_order": ("in", work_order_names), "docstatus": ("<", 2)},
		fields=["work_order", {"COUNT": "name", "as": "job_card_count"}],
		group_by="work_order",
	):
		counts[row.work_order] = row.job_card_count
	return counts


def get_job_card_actual_times(job_card_names):
	actual_times = {}
	for row in frappe.get_all(
		"Job Card Time Log",
		filters={"parent": ("in", job_card_names), "docstatus": ("<", 2)},
		fields=["parent", {"SUM": "time_in_mins", "as": "actual_time"}],
		group_by="parent",
	):
		actual_times[row.parent] = flt(row.actual_time)
	return actual_times


def get_timesheet_task_actual_cost_by_project(project_names, from_date, to_date):
	"""Task actual cost from submitted Timesheet Detail rows (Production Cost Summary)."""
	if not project_names:
		return {}

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
		{"projects": project_names, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)

	return {
		row.project: {
			"timesheet_task_count": row.timesheet_task_count,
			"task_actual_cost": flt(row.task_actual_cost),
		}
		for row in rows
	}


def get_task_metrics(project_names, from_date, to_date):
	"""Scheduled and actual task cost per project (Production Cost Summary)."""
	if not project_names:
		return {}

	project_costs = {
		row.name: flt(row.estimated_costing)
		for row in frappe.get_all(
			"Project",
			filters={"name": ("in", project_names)},
			fields=["name", "estimated_costing"],
		)
	}
	timesheet_metrics = get_timesheet_task_actual_cost_by_project(project_names, from_date, to_date)

	metrics = {}
	for project in project_names:
		timesheet = timesheet_metrics.get(project, {})
		metrics[project] = {
			"timesheet_task_count": timesheet.get("timesheet_task_count", 0),
			"task_scheduled_cost": project_costs.get(project, 0),
			"task_actual_cost": timesheet.get("task_actual_cost", 0),
		}

	return metrics
