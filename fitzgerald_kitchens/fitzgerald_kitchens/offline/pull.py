# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""The read side of the sync protocol — kept separate from the generic push/
status engine (`fitzgerald_kitchens.offline_engine`) because *what* to send
back (assigned tasks, their Development Units) is inherently domain-specific,
while push/status/catalog stay generic and hook-based so any other app
installed on this bench could register its own operations/catalog entries
without depending on this module.
"""

import frappe
from frappe.utils import now_datetime

DEFAULT_PULL_LIMIT = 100


@frappe.whitelist()
def pull(cursor: str | None = None, device_id: str | None = None, limit: int = DEFAULT_PULL_LIMIT):
	"""Incremental read side of the sync protocol.

	`cursor` is a single ISO datetime watermark — the max `modified` value
	the device has already seen — not per-doctype, to keep client bookkeeping
	simple. Scoped to the current user's assigned tasks (same scoping as
	`get_my_tasks_dashboard`) and the Development Units under those tasks'
	projects. Child tables (stages/evidence/labour/material/issues) aren't
	independently cursor-filterable in Frappe, so the full set is always
	sent for any Development Unit whose `modified` moved since the cursor.

	Paginate by calling again with the same `cursor` while `has_more` is
	true; only advance to `next_cursor` once `has_more` is false, so a
	record modified mid-pull is never silently skipped.
	"""
	from fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.my_tasks import (
		_collect_assigned_task_names,
	)

	limit = int(limit) if limit else DEFAULT_PULL_LIMIT
	next_cursor = now_datetime()

	from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import enabled_pull_keys, settings_enabled

	# When Offline Sync Settings is on, only pull data for selected Offline Items.
	# When settings are off, keep legacy behaviour (pull everything).
	if settings_enabled():
		pull_keys = enabled_pull_keys(app_name="fitzgerald_kitchens")
	else:
		pull_keys = {"tasks", "development_units"}

	task_names = _collect_assigned_task_names(frappe.session.user)

	tasks = []
	if "tasks" in pull_keys and task_names:
		task_filters = {"name": ["in", task_names]}
		if cursor:
			task_filters["modified"] = [">", cursor]
		tasks = frappe.get_all(
			"Task",
			filters=task_filters,
			fields=["name", "subject", "project", "status", "progress", "modified"],
			order_by="modified asc",
			limit_page_length=limit,
		)

	# Projects from assigned tasks — needed for Development Unit scope
	project_names = []
	if task_names and ("tasks" in pull_keys or "development_units" in pull_keys):
		project_names = list(
			{
				row.project
				for row in frappe.get_all("Task", filters={"name": ["in", task_names]}, fields=["project"])
				if row.project
			}
		)

	development_units = []
	if "development_units" in pull_keys and project_names:
		du_filters = {"project": ["in", project_names]}
		if cursor:
			du_filters["modified"] = [">", cursor]
		du_names = frappe.get_all(
			"Development Unit",
			filters=du_filters,
			pluck="name",
			order_by="modified asc",
			limit_page_length=limit,
		)
		for name in du_names:
			if not frappe.has_permission("Development Unit", doc=name, ptype="read"):
				continue
			doc = frappe.get_doc("Development Unit", name)
			development_units.append(
				{
					"name": doc.name,
					"unit_reference": doc.unit_reference,
					"project": doc.project,
					"customer": doc.customer,
					"current_stage": doc.current_stage,
					"current_stage_progress": doc.current_stage_progress,
					"modified": str(doc.modified),
					"stages": [
						{
							"name": row.name,
							"sequence": row.sequence,
							"stage": row.stage,
							"status": row.status,
							"progress_percentage": row.progress_percentage,
							"planned_date": str(row.planned_date) if row.planned_date else None,
							"actual_completion_date": str(row.actual_completion_date)
							if row.actual_completion_date
							else None,
							"notes": row.notes,
						}
						for row in doc.stages
					],
					"issues": [
						{
							"name": row.name,
							"issue_type": row.issue_type,
							"description": row.description,
							"severity": row.severity,
							"status": row.status,
						}
						for row in doc.issues
					],
				}
			)

	has_more = len(tasks) >= limit or len(development_units) >= limit

	return {
		"tasks": tasks,
		"development_units": development_units,
		"next_cursor": str(next_cursor),
		"has_more": has_more,
	}
