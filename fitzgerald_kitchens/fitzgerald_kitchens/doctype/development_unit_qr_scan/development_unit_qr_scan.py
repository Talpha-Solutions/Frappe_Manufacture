# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from fitzgerald_kitchens.fitzgerald_kitchens.utils.stage_tracking import (
	apply_stage_row_update,
	get_stage_rows_for_unit,
	normalize_stage_status,
	resolve_development_unit_from_qr,
	sync_unit_progress_from_stages,
)


class DevelopmentUnitQRScan(Document):
	def validate(self):
		if not self.scanned_by:
			self.scanned_by = frappe.session.user
		if not self.scan_datetime:
			self.scan_datetime = now_datetime()

	def before_submit(self):
		self.apply_stage_updates()

	def apply_stage_updates(self) -> None:
		if not self.development_unit:
			frappe.throw(_("Development Unit is required"))

		du = frappe.get_doc("Development Unit", self.development_unit)
		lines_by_row = {
			line.stage_row_name: line for line in self.scan_lines if line.stage_row_name
		}
		updated = False

		for stage_row in du.stages:
			line = lines_by_row.get(stage_row.name)
			if not line or not line.updated_status:
				continue

			new_status = normalize_stage_status(line.updated_status)
			if new_status == stage_row.status and not (line.process_tracked or self.process_tracked):
				continue

			apply_stage_row_update(
				stage_row,
				new_status,
				process_tracked=bool(line.process_tracked or self.process_tracked),
			)
			if line.remarks:
				stage_row.notes = line.remarks
			updated = True

		if not updated:
			frappe.throw(_("Set Updated Status on at least one stage before submitting"))

		sync_unit_progress_from_stages(du)
		du.save()


@frappe.whitelist()
def resolve_qr_code(qr_text: str):
	"""Resolve scanned QR text to a Development Unit."""
	development_unit = resolve_development_unit_from_qr(qr_text)
	doc = frappe.get_doc("Development Unit", development_unit)
	return {
		"development_unit": development_unit,
		"unit_reference": doc.unit_reference,
		"project": doc.project,
		"customer": doc.customer,
	}


@frappe.whitelist()
def get_stages_for_qr_scan(development_unit: str):
	"""Load Development Unit stages into QR scan lines."""
	if not development_unit or not frappe.db.exists("Development Unit", development_unit):
		frappe.throw(_("Development Unit {0} does not exist").format(development_unit))

	return get_stage_rows_for_unit(development_unit)
