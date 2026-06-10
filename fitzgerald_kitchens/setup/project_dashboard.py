# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

PRODUCTION_PLAN_DOCTYPE = "Production Plan"


def get_project_dashboard(data):
	"""Extend Project connections dashboard with linked Production Plans."""
	manufacture_label = _("Manufacture")
	added = False

	for group in data.get("transactions") or []:
		if group.get("label") == manufacture_label:
			items = group.setdefault("items", [])
			if PRODUCTION_PLAN_DOCTYPE not in items:
				items.append(PRODUCTION_PLAN_DOCTYPE)
			added = True
			break

	if not added:
		data.setdefault("transactions", []).append(
			{"label": manufacture_label, "items": [PRODUCTION_PLAN_DOCTYPE]}
		)

	data["method"] = "fitzgerald_kitchens.setup.project_dashboard.get_project_open_count"
	return data


@frappe.whitelist()
@frappe.read_only()
def get_project_open_count(doctype: str, name: str, items=None):
	"""Count dashboard links for Project, including Production Plans via child table."""
	from frappe.desk.notifications import _get_linked_document_counts

	result = _get_linked_document_counts(doctype, name, items)
	count = result["count"]

	count["external_links_found"] = [
		row for row in count.get("external_links_found", []) if row.get("doctype") != PRODUCTION_PLAN_DOCTYPE
	]

	plan_names = get_production_plan_names_for_project(name)
	if plan_names:
		count.setdefault("internal_links_found", []).append(
			{
				"doctype": PRODUCTION_PLAN_DOCTYPE,
				"count": len(plan_names),
				"open_count": get_open_production_plan_count(plan_names),
				"names": plan_names,
			}
		)

	return result


def get_production_plan_names_for_project(project: str) -> list[str]:
	"""Return Production Plan names linked to a project."""
	project = (project or "").strip()
	if not project:
		return []

	plan_names: set[str] = set()

	plan_names.update(
		frappe.get_all(
			"Production Plan Project",
			filters={"project": project, "parenttype": PRODUCTION_PLAN_DOCTYPE},
			pluck="parent",
		)
	)

	plan_names.update(
		frappe.get_all(
			PRODUCTION_PLAN_DOCTYPE,
			filters={"project": project},
			pluck="name",
		)
	)

	plan_names.update(
		frappe.db.sql(
			"""
			SELECT DISTINCT parent
			FROM `tabProduction Plan Item`
			WHERE fk_project = %s AND parenttype = %s
			""",
			(project, PRODUCTION_PLAN_DOCTYPE),
			pluck=True,
		)
	)

	return sorted(name for name in plan_names if name and frappe.db.exists(PRODUCTION_PLAN_DOCTYPE, name))


def get_open_production_plan_count(plan_names: list[str]) -> int:
	if not plan_names:
		return 0

	return frappe.db.count(
		PRODUCTION_PLAN_DOCTYPE,
		{
			"name": ["in", plan_names],
			"docstatus": ["!=", 2],
			"status": ["not in", ["Cancelled", "Closed"]],
		},
	)
