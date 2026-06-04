# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from fitzgerald_kitchens.workbook_import.import_messages import normalize_import_log_fields


class DevelopmentWorkbookImport(Document):
	def validate(self):
		if self.is_new() and not self.company:
			self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
				"Global Defaults", "default_company"
			)
		normalize_import_log_fields(self)

	@frappe.whitelist()
	def fix_legacy_log_fields(self):
		from fitzgerald_kitchens.workbook_import.import_messages import normalize_import_log_fields

		if normalize_import_log_fields(self):
			self.save(ignore_permissions=True)
		return {"fixed": True}

	@frappe.whitelist()
	def validate_workbook(self):
		from fitzgerald_kitchens.workbook_import.import_messages import validate_template_options
		from fitzgerald_kitchens.workbook_import.runner import validate_import

		validate_template_options(self)
		self.save(ignore_permissions=True)
		return validate_import(self.name)

	@frappe.whitelist()
	def run_workbook_import(self):
		from fitzgerald_kitchens.workbook_import.import_messages import validate_template_options
		from fitzgerald_kitchens.workbook_import.runner import enqueue_import

		if self.import_status != "Ready":
			frappe.throw(frappe._("Validate the file first. Import status must be Ready."))

		validate_template_options(self)
		self.save(ignore_permissions=True)
		enqueue_import(self.name)
		return {"queued": True}
