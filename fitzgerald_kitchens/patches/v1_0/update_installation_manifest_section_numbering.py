# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	path = frappe.get_app_path(
		"fitzgerald_kitchens",
		"fitzgerald_kitchens",
		"print_format",
		"installation_manifest",
		"installation_manifest.json",
	)
	import_file_by_path(path, force=True)
