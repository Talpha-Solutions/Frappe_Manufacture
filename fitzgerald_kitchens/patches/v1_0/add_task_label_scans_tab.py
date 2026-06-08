# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe


def execute():
	_add_task_label_scans_tab()


def _add_task_label_scans_tab():
	fields = [
		{
			"fieldname": "custom_label_scans",
			"fieldtype": "Tab Break",
			"label": "Label Scans",
			"insert_after": "custom_uploader_target",
		},
		{
			"fieldname": "custom_label_scans_target",
			"fieldtype": "HTML",
			"label": "Scanned Labels",
			"insert_after": "custom_label_scans",
		},
	]

	for field in fields:
		if frappe.db.exists("Custom Field", {"dt": "Task", "fieldname": field["fieldname"]}):
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Task",
				**field,
			}
		)
		doc.insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Task")
