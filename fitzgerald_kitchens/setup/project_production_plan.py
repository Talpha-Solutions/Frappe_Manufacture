# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today

from fitzgerald_kitchens.manufacturing.project_manifest import resolve_project_effective_manifest
from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE


@frappe.whitelist()
def make_production_plan_from_project(project: str):
	"""Return a new Production Plan draft pre-filled from a unit project."""
	project_doc = frappe.get_doc("Project", project)
	project_doc.check_permission("read")
	frappe.has_permission("Production Plan", ptype="create", throw=True)

	if project_doc.project_type == SITE_PROJECT_TYPE:
		frappe.throw(_("Production Plan can only be created from unit projects, not Site projects."))

	if not project_doc.company:
		frappe.throw(_("Project {0} has no Company set.").format(project_doc.name))

	effective_manifest = resolve_project_effective_manifest(project_doc.name)
	if not effective_manifest:
		frappe.throw(_("Set Effective Manifest on the Unit tab first."))

	plan = frappe.new_doc("Production Plan")
	plan.company = project_doc.company
	plan.posting_date = today()
	plan.get_items_from = "Project"

	if project_doc.get("customer"):
		plan.customer = project_doc.customer

	if project_doc.get("fk_parent_project"):
		plan.fk_project_site = project_doc.fk_parent_project

	plan.project = project_doc.name

	plan.append(
		"fk_projects",
		{
			"project": project_doc.name,
			"project_name": project_doc.project_name,
			"project_type": project_doc.project_type,
			"effective_manifest": effective_manifest,
			"status": project_doc.status,
		},
	)

	return plan.as_dict()
