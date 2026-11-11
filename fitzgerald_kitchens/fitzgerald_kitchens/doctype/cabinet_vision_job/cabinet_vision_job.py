# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import os

import frappe
from frappe import _
from frappe.model.document import Document

EXPORT_SCRIPT = "export_cabinet_vision.ps1"


class CabinetVisionJob(Document):
	def validate(self):
		if not self.job_name:
			self.job_name = _("New Cabinet Vision Job")

	def on_trash(self):
		with_bom = frappe.get_all("Cabinet Vision Cabinet", filters={"job": self.name, "bom": ["is", "set"]}, pluck="name")
		if with_bom:
			frappe.throw(
				_("Cabinets {0} have BOMs made from them, so this job can't be deleted.").format(", ".join(with_bom))
			)
		for name in frappe.get_all("Cabinet Vision Cabinet", filters={"job": self.name}, pluck="name"):
			frappe.delete_doc("Cabinet Vision Cabinet", name, ignore_permissions=True)


@frappe.whitelist()
def import_export_file(job: str) -> dict:
	"""Build the job's rooms, cabinets, parts and materials from its attached export."""
	from fitzgerald_kitchens.fitzgerald_kitchens.doctype.cabinet_vision_job.cabinet_vision_import import import_job

	return import_job(job)


@frappe.whitelist()
def download_export_script():
	"""The PowerShell script that exports a restored Cabinet Vision report database to JSON."""
	with open(os.path.join(os.path.dirname(__file__), EXPORT_SCRIPT), "rb") as fh:
		content = fh.read()
	frappe.response["filename"] = EXPORT_SCRIPT
	frappe.response["filecontent"] = content
	frappe.response["type"] = "download"
