import frappe
from frappe import _

from fitzgerald_kitchens.fitzgerald_kitchens.website.project_card import enrich_projects_with_current_stage


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("You need to be logged in to view projects."), frappe.PermissionError)

	context.no_cache = 1
	context.show_sidebar = True
	context.title = _("Projects")

	txt = frappe.form_dict.get("txt", "")
	status_filter = frappe.form_dict.get("status", "")

	context.projects = _get_projects(txt=txt, status_filter=status_filter)
	context.txt = txt
	context.status_filter = status_filter

	context.no_result_message = _("No projects found.")


def _get_projects(txt="", status_filter=""):
	filters = {}
	or_filters = []

	if status_filter:
		filters["status"] = status_filter

	if txt:
		or_filters = [
			["Project", "project_name", "like", f"%{txt}%"],
			["Project", "name", "like", f"%{txt}%"],
		]

	try:
		projects = frappe.get_list(
			"Project",
			fields=[
				"name",
				"project_name",
				"status",
				"percent_complete",
				"customer",
				"expected_start_date",
				"expected_end_date",
				"description",
				"_assign",
				"modified",
			],
			filters=filters,
			or_filters=or_filters,
			order_by="creation asc",
			limit_page_length=50,
		)
	except frappe.PermissionError:
		projects = []

	for project in projects:
		if project.percent_complete:
			project.progress_int = int(round(project.percent_complete))
			if project.progress_int >= 100:
				project.progress_class = "success"
			elif project.progress_int >= 50:
				project.progress_class = "info"
			else:
				project.progress_class = "warning"
		else:
			project.progress_int = 0
			project.progress_class = "secondary"

		project.status_class = _get_status_class(project.status)

		if project._assign:
			import json
			assigned_users = json.loads(project._assign)
			project.assigned_users = _get_user_details(assigned_users[:3])
		else:
			project.assigned_users = []

	enrich_projects_with_current_stage(projects)
	return projects


def _get_status_class(status):
	mapping = {
		"Open": "primary",
		"Completed": "success",
		"Cancelled": "danger",
		"Template": "secondary",
	}
	return mapping.get(status, "secondary")


def _get_user_details(users):
	result = []
	for user in users:
		details = frappe.db.get_value(
			"User", user, ["full_name", "user_image"], as_dict=True
		)
		if details:
			result.append(details)
	return result
