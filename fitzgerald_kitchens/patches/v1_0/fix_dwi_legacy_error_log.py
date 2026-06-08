# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.workbook_import.import_messages import (
	is_legacy_success_message,
	normalize_import_log_fields,
)


def execute():
	names = frappe.get_all(
		"Development Workbook Import",
		filters={"import_status": ["in", ["Ready", "Completed"]]},
		pluck="name",
	)
	for name in names:
		doc = frappe.get_doc("Development Workbook Import", name)
		if not is_legacy_success_message(doc.error_log):
			continue
		if normalize_import_log_fields(doc):
			doc.save(ignore_permissions=True)
	frappe.db.commit()
