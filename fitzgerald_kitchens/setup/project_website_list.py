# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.fitzgerald_kitchens.website.project_card import enrich_projects_with_current_stage

PROJECT_LIST_ORDER_BY = "creation asc"
TASK_LIST_ORDER_BY = "creation asc"


def patch_project_website_list():
	"""Add current task stage data and oldest-first ordering to project website lists."""
	import erpnext.projects.doctype.project.project as erp_project

	if getattr(erp_project, "_fk_project_list_patched_v3", False):
		return

	if not hasattr(erp_project, "_fk_original_get_project_list"):
		erp_project._fk_original_get_project_list = erp_project.get_project_list
	if not hasattr(erp_project, "_fk_original_get_list_context"):
		erp_project._fk_original_get_list_context = erp_project.get_list_context

	original_get_project_list = erp_project._fk_original_get_project_list
	original_get_list_context = erp_project._fk_original_get_list_context

	def get_project_list(
		doctype,
		txt,
		filters,
		limit_start,
		limit_page_length=20,
		order_by=PROJECT_LIST_ORDER_BY,
	):
		if not order_by or order_by == "creation desc":
			order_by = PROJECT_LIST_ORDER_BY

		projects = original_get_project_list(
			doctype, txt, filters, limit_start, limit_page_length, order_by
		)
		enrich_projects_with_current_stage(projects)
		return projects

	def get_list_context(context=None):
		list_context = frappe._dict(original_get_list_context(context) or {})
		list_context.order_by = PROJECT_LIST_ORDER_BY
		list_context.get_list = get_project_list
		return list_context

	erp_project.get_project_list = get_project_list
	erp_project.get_list_context = get_list_context
	erp_project._fk_project_list_patched_v3 = True


def patch_project_website_tasks():
	"""Show oldest tasks first and schedule status on the project website task list."""
	import erpnext.templates.pages.projects as projects_page

	if getattr(projects_page, "_fk_project_tasks_patched_v2", False):
		return

	TASK_ROW_TEMPLATE = "fitzgerald_kitchens/templates/includes/projects/project_tasks.html"

	def get_tasks(project, start=0, search=None, item_status=None):
		filters = {"project": project}
		if search:
			filters["subject"] = ("like", f"%{search}%")

		tasks = frappe.get_all(
			"Task",
			filters=filters,
			fields=[
				"name",
				"subject",
				"status",
				"modified",
				"_assign",
				"exp_end_date",
				"completed_on",
				"is_group",
				"parent_task",
			],
			order_by=TASK_LIST_ORDER_BY,
			limit_start=start,
			limit_page_length=100,
		)

		from fitzgerald_kitchens.fitzgerald_kitchens.website.project_card import (
			enrich_tasks_with_schedule_status,
		)

		enrich_tasks_with_schedule_status(tasks)

		for task in tasks:
			if task.is_group:
				child_tasks = [row for row in tasks if row.parent_task == task.name]
				if child_tasks:
					task.children = child_tasks

			# Retrieve attached images for image preview modal compatibility
			attachments = frappe.get_all(
				"File",
				filters={
					"attached_to_doctype": "Task",
					"attached_to_name": task.name,
					"is_private": 0
				},
				fields=["file_url", "file_name"]
			)
			task.attached_images = [
				att for att in attachments 
				if att.file_url and att.file_url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
			]
			task.image_count = len(task.attached_images)

		return [task for task in tasks if not task.parent_task]

	def get_task_html(project, start=0, item_status=None):
		return frappe.render_template(
			TASK_ROW_TEMPLATE,
			{
				"doc": {
					"name": project,
					"project_name": project,
					"tasks": get_tasks(project, start, item_status=item_status),
				}
			},
			is_path=True,
		)

	projects_page.get_tasks = get_tasks
	if hasattr(projects_page, "get_task_html"):
		projects_page.get_task_html = get_task_html
	projects_page._fk_project_tasks_patched_v2 = True
