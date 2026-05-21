# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from fitzgerald_kitchens.setup.development_stages import (
	STANDARD_DEVELOPMENT_STAGES,
	STANDARD_STAGES_BY_NAME,
	normalize_evidence_required,
)


class DevelopmentStageSettings(Document):
	def validate(self):
		self.validate_unique_stage_names()
		self.normalize_stage_rows()

	def on_update(self):
		sync_stages_to_master(self)

	def validate_unique_stage_names(self):
		names = [row.stage_name for row in self.stages if row.stage_name]
		if len(names) != len(set(names)):
			frappe.throw(_("Each stage name must be unique."))

	def normalize_stage_rows(self):
		for row in self.stages:
			row.evidence_required = normalize_evidence_required(row.evidence_required)


def sync_stages_to_master(settings_doc):
	stage_names_in_settings = set()

	for row in settings_doc.stages:
		if not row.stage_name:
			continue

		stage_names_in_settings.add(row.stage_name)
		values = {
			"stage_name": row.stage_name,
			"sequence": row.sequence,
			"default_progress_percentage": row.default_progress_percentage,
			"evidence_required": normalize_evidence_required(row.evidence_required),
			"customer_visible": row.customer_visible,
			"stage_category": row.stage_category,
		}

		if frappe.db.exists("Development Stage", row.stage_name):
			master = frappe.get_doc("Development Stage", row.stage_name)
			master.update(values)
			master.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "Development Stage", **values}).insert(ignore_permissions=True)

	for name in frappe.get_all("Development Stage", pluck="name"):
		if name not in stage_names_in_settings:
			frappe.delete_doc("Development Stage", name, force=True, ignore_permissions=True)


@frappe.whitelist()
def ensure_default_stages_for_form():
	"""Populate the settings table with standard stages when empty (page load)."""
	doc = frappe.get_single("Development Stage Settings")

	if doc.stages:
		return None

	for stage in STANDARD_DEVELOPMENT_STAGES:
		doc.append("stages", stage)

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return True
