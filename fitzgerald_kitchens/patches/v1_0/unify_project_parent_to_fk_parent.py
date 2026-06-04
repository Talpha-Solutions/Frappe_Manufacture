# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.setup.project_hierarchy_fields import remove_project_hierarchy_fields


def execute():
	if frappe.db.has_column("Project", "parent_project"):
		frappe.db.sql(
			"""
			UPDATE `tabProject`
			SET fk_parent_project = parent_project
			WHERE (fk_parent_project IS NULL OR fk_parent_project = '')
				AND parent_project IS NOT NULL AND parent_project != ''
			"""
		)

	remove_project_hierarchy_fields()
	frappe.db.commit()
