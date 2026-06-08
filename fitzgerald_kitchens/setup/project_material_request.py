# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from fitzgerald_kitchens.setup.manifest_line_labels import (
	LABEL_CATEGORY_ASSEMBLY,
	resolve_label_category,
)
from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE


@frappe.whitelist()
def make_material_request_from_project(project: str):
	"""Create a draft Material Request with items from the project's effective manifest."""
	project_doc = frappe.get_doc("Project", project)
	project_doc.check_permission("read")
	frappe.has_permission("Material Request", ptype="create", throw=True)

	if project_doc.project_type == SITE_PROJECT_TYPE:
		frappe.throw(_("Material Request can only be created from unit projects, not Site projects."))

	manifest_name = project_doc.get("fk_effective_manifest")
	if not manifest_name:
		frappe.throw(_("Set Effective Manifest on the Unit tab first."))

	if not frappe.db.exists("Manifest", manifest_name):
		frappe.throw(_("Manifest '{0}' was not found.").format(manifest_name))

	manifest = frappe.get_doc("Manifest", manifest_name)
	items = _manifest_lines_for_material_request(manifest, project_doc.name)
	if not items:
		frappe.throw(
			_("No non-BOM manifest items found. Material Request only includes Fitting Kit and Extra lines.")
		)

	mr = frappe.new_doc("Material Request")
	mr.company = project_doc.company
	mr.material_request_type = "Purchase"
	if project_doc.get("project_name"):
		mr.title = project_doc.project_name

	for row in items:
		mr.append("items", row)

	return mr.as_dict()


def _manifest_lines_for_material_request(manifest, project_name: str) -> list[dict]:
	rows: list[dict] = []

	for line in manifest.items:
		if not line.item_code or flt(line.qty) <= 0:
			continue

		category = (line.label_category or "").strip() or resolve_label_category(
			line.item_code, line.linked_bom
		)
		if category == LABEL_CATEGORY_ASSEMBLY:
			continue

		row = {
			"item_code": line.item_code,
			"qty": flt(line.qty),
			"project": project_name,
		}
		if line.get("description"):
			row["description"] = line.description
		if line.get("uom"):
			row["uom"] = line.uom
			row["stock_uom"] = line.uom

		rows.append(row)

	return rows
