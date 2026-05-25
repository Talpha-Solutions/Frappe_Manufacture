# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.setup.project_bom_fields import ensure_project_bom_fields


def execute():
	ensure_project_bom_fields()
	_update_bom_tab_insert_after()


def _update_bom_tab_insert_after() -> None:
	"""Existing sites may have BOM tab directly after message; chain it after Connections."""
	name = "Project-bom_tab"
	if not frappe.db.exists("Custom Field", name):
		return

	if frappe.db.get_value("Custom Field", name, "insert_after") == "connections_tab":
		return

	frappe.db.set_value("Custom Field", name, "insert_after", "connections_tab", update_modified=False)
