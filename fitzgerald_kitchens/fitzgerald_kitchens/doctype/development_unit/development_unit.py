# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from fitzgerald_kitchens.setup.development_stages import get_default_unit_stage_rows


class DevelopmentUnit(Document):
	def before_insert(self):
		self.set_default_stages_if_empty()

	def set_default_stages_if_empty(self):
		if self.stages:
			return

		for row in get_default_unit_stage_rows():
			self.append("stages", row)


@frappe.whitelist()
def get_default_stages():
	"""Return standard stage rows for the Development Unit Stages table (form load)."""
	from fitzgerald_kitchens.setup.install import ensure_development_stage_settings

	ensure_development_stage_settings()
	return get_default_unit_stage_rows()
