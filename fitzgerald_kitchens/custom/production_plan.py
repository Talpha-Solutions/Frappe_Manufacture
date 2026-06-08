# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime

from erpnext.manufacturing.doctype.production_plan.production_plan import ProductionPlan
from fitzgerald_kitchens.manufacturing.project_manifest import (
	get_manifest_items_for_project,
	get_projects_for_production_plan,
	resolve_project_effective_manifest,
)


class FKProductionPlan(ProductionPlan):
	@frappe.whitelist()
	def get_open_projects(self):
		"""Pull projects based on criteria selected."""
		open_projects = get_projects_for_production_plan(self)

		if open_projects:
			self.set("fk_projects", [])
			for data in open_projects:
				self.append(
					"fk_projects",
					{
						"project": data.name,
						"project_name": data.project_name,
						"project_type": data.project_type,
						"effective_manifest": data.effective_manifest,
						"status": data.status,
					},
				)
		else:
			active_filters = []
			if self.get("customer"):
				active_filters.append(_("Customer: {0}").format(self.customer))
			if self.get("fk_project_site"):
				site_name = frappe.db.get_value("Project", self.fk_project_site, "project_name") or self.fk_project_site
				active_filters.append(_("Project Site: {0}").format(site_name))

			message = _("No projects found for company {0}.").format(self.company)
			if active_filters:
				message += " " + _("Check Filters — {0}.").format(", ".join(active_filters))
			else:
				other_companies = frappe.get_all(
					"Project",
					filters={"company": ["!=", self.company]},
					fields=["company"],
					group_by="company",
					pluck="company",
				)
				if other_companies:
					message += " " + _("Projects also exist under: {0}.").format(
						", ".join(sorted(set(other_companies)))
					)

			frappe.msgprint(message, indicator="orange", title=_("No Projects Found"))

	@frappe.whitelist()
	def get_items(self):
		self.set("po_items", [])
		if self.get_items_from == "Project":
			self.get_project_items()
		else:
			super().get_items()

	def get_project_items(self):
		project_list = [row.project for row in self.get("fk_projects", []) if row.project]
		if not project_list:
			frappe.throw(_("Please fill the Projects table"), title=_("Projects Required"))

		skipped_projects: list[str] = []
		for project in project_list:
			effective_manifest = resolve_project_effective_manifest(project)
			if not effective_manifest:
				skipped_projects.append(project)
				continue

			manifest_items = get_manifest_items_for_project(project, effective_manifest)
			if not manifest_items:
				skipped_projects.append(project)
				continue

			for item in manifest_items:
				pi = self.append(
					"po_items",
					{
						"item_code": item["item_code"],
						"description": item["description"],
						"stock_uom": item["stock_uom"],
						"bom_no": item["bom_no"],
						"planned_qty": item["qty"],
						"pending_qty": item["qty"],
						"planned_start_date": now_datetime(),
						"fk_project": project,
					},
				)
				pi._set_defaults()

		if skipped_projects:
			frappe.msgprint(
				_("Skipped projects without Effective Manifest or manifest items: {0}").format(
					", ".join(skipped_projects)
				),
				indicator="orange",
				title=_("Projects Skipped"),
			)

		if not self.get("po_items"):
			frappe.throw(
				_("No manufacturing items found in the Effective Manifest for the selected projects"),
				title=_("Items Required"),
			)

		self.calculate_total_planned_qty()

	def get_production_items(self):
		item_dict = super().get_production_items()
		if self.get_items_from != "Project":
			return item_dict

		po_projects = {row.name: row.get("fk_project") or self.project for row in self.po_items}
		for details in item_dict.values():
			production_plan_item = details.get("production_plan_item")
			if production_plan_item in po_projects:
				details["project"] = po_projects[production_plan_item]

		return item_dict
