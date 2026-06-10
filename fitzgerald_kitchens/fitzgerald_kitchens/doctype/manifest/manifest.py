# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from fitzgerald_kitchens.setup.manifest_line_labels import sync_manifest_line_labels


class Manifest(Document):
	def before_save(self):
		for line in self.items:
			sync_manifest_line_labels(line)
