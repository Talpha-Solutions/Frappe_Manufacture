# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.workbook_import.manifest_resolver import resolve_effective_manifest


def execute():
	projects = frappe.get_all(
		"Project",
		filters={
			"project_type": ["!=", "Site"],
			"fk_unit_configuration": ["is", "set"],
		},
		fields=["name", "fk_unit_configuration", "project_type", "fk_effective_manifest"],
	)

	updated = 0
	for project in projects:
		if project.fk_effective_manifest:
			continue

		manifest = resolve_effective_manifest(
			project.fk_unit_configuration, project.project_type
		)
		if not manifest:
			continue

		frappe.db.set_value(
			"Project",
			project.name,
			"fk_effective_manifest",
			manifest,
			update_modified=False,
		)
		updated += 1

	if updated:
		frappe.db.commit()
