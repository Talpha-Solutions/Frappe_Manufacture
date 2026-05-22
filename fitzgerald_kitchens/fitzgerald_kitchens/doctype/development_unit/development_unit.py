# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from io import BytesIO

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.file_manager import save_file

from fitzgerald_kitchens.fitzgerald_kitchens.utils.stage_tracking import (
	get_qr_code_value,
	sync_unit_progress_from_stages,
)
from fitzgerald_kitchens.setup.development_stages import get_default_unit_stage_rows


class DevelopmentUnit(Document):
	def before_insert(self):
		self.set_default_stages_if_empty()

	def before_save(self):
		if self.name and not self.name.startswith("new-"):
			self.qr_code = get_qr_code_value(self.name)
		if self.stages:
			sync_unit_progress_from_stages(self)

	def after_insert(self):
		self._auto_generate_qr_code()

	def on_update(self):
		self._auto_generate_qr_code()

	def _auto_generate_qr_code(self) -> None:
		if frappe.flags.in_import or not self.name or self.name.startswith("new-"):
			return

		expected_value = get_qr_code_value(self.name)
		if self.qr_code_image and self.qr_code == expected_value:
			return

		self.qr_code = expected_value
		file_url = self.generate_qr_code_image()
		frappe.db.set_value(
			self.doctype,
			self.name,
			{"qr_code": self.qr_code, "qr_code_image": file_url},
			update_modified=False,
		)

	def set_default_stages_if_empty(self):
		if self.stages:
			return

		for row in get_default_unit_stage_rows():
			self.append("stages", row)

	def generate_qr_code_image(self) -> str:
		if not self.name or self.name.startswith("new-"):
			return ""

		value = self.qr_code or get_qr_code_value(self.name)
		self.qr_code = value

		try:
			from pyqrcode import create as qrcreate
		except ImportError:
			frappe.throw(_("QR code library is not installed. Contact your system administrator."))

		buffer = BytesIO()
		try:
			qrcreate(value).png(buffer, scale=6, quiet_zone=2)
			png_content = buffer.getvalue()
		finally:
			buffer.close()

		self._delete_qr_code_file()

		file_doc = save_file(
			f"{self.name}-qr.png",
			png_content,
			self.doctype,
			self.name,
			is_private=0,
			df="qr_code_image",
		)
		self.qr_code_image = file_doc.file_url
		return file_doc.file_url

	def _delete_qr_code_file(self) -> None:
		if not self.qr_code_image:
			return

		file_id = frappe.db.get_value("File", {"file_url": self.qr_code_image}, "name")
		if file_id:
			frappe.delete_doc("File", file_id, ignore_permissions=True)

		self.qr_code_image = None


@frappe.whitelist()
def get_default_stages():
	"""Return standard stage rows for the Development Unit Stages table (form load)."""
	from fitzgerald_kitchens.setup.install import ensure_development_stage_settings

	ensure_development_stage_settings()
	return get_default_unit_stage_rows()


@frappe.whitelist()
def get_kitchen_bom_from_mapping(kitchen_type: str, kitchen_specification: str):
	"""Return Kitchen BOM and Item for the selected type + specification."""
	from fitzgerald_kitchens.fitzgerald_kitchens.doctype.kitchen_bom_mapping.kitchen_bom_mapping import (
		get_kitchen_bom_for_mapping,
	)

	return get_kitchen_bom_for_mapping(kitchen_type, kitchen_specification)


@frappe.whitelist()
def get_wardrobe_bom_from_mapping(wardrobe_type: str, wardrobe_specification: str):
	"""Return Wardrobe BOM and Item for the selected type + specification."""
	from fitzgerald_kitchens.fitzgerald_kitchens.doctype.wardrobe_bom_mapping.wardrobe_bom_mapping import (
		get_wardrobe_bom_for_mapping,
	)

	return get_wardrobe_bom_for_mapping(wardrobe_type, wardrobe_specification)
