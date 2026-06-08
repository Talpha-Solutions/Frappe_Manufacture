# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe


def execute():
	_add_custom_fields()
	frappe.clear_cache(doctype="Task")
	frappe.clear_cache(doctype="Material Request")


def _add_custom_fields():
	fields = [
		{
			"dt": "Task",
			"fieldname": "custom_despatch_material_request",
			"fieldtype": "Link",
			"label": "Despatch Material Request",
			"options": "Material Request",
			"insert_after": "project",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"dt": "Material Request",
			"fieldname": "custom_scan_task",
			"fieldtype": "Link",
			"label": "Scan Task",
			"options": "Task",
			"insert_after": "project",
			"read_only": 1,
			"no_copy": 1,
		},
	]

	for field in fields:
		if frappe.db.exists("Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}):
			continue

		frappe.get_doc({"doctype": "Custom Field", **field}).insert(ignore_permissions=True)
