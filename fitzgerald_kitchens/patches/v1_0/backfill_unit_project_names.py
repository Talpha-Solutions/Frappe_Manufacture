# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE
from fitzgerald_kitchens.workbook_import.naming import build_unit_project_name


def execute():
	updated = 0
	projects = frappe.get_all(
		"Project",
		filters={
			"project_type": ["!=", SITE_PROJECT_TYPE],
			"fk_house_number": ["is", "set"],
			"fk_parent_project": ["is", "set"],
		},
		fields=["name", "project_name", "project_type", "fk_house_number", "fk_parent_project"],
	)

	for project in projects:
		site_name = frappe.db.get_value("Project", project.fk_parent_project, "project_name")
		if not site_name:
			continue

		new_name = build_unit_project_name(
			site_name,
			project.fk_house_number,
			project.project_type,
		)
		if project.project_name == new_name:
			continue

		frappe.db.set_value(
			"Project",
			project.name,
			"project_name",
			new_name,
			update_modified=False,
		)
		updated += 1

	if updated:
		frappe.db.commit()
