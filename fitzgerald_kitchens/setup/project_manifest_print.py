# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import base64
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from fitzgerald_kitchens.fitzgerald_kitchens.utils.qr_codes import generate_qr_png_bytes
from fitzgerald_kitchens.workbook_import.naming import format_unit_location_label
from fitzgerald_kitchens.setup.manifest_line_labels import (
	LABEL_CATEGORY_ASSEMBLY,
	LABEL_CATEGORY_EXTRA,
	LABEL_CATEGORY_FITTING,
	resolve_label_category,
)

SECTION_ASSEMBLY = "assembly"
SECTION_FITTING = "fitting_kit"
SECTION_EXTRA = "extra"

SECTION_DEFINITIONS = (
	(SECTION_ASSEMBLY, "ASSEMBLY (CABINETRY & CARCASSES)", "fk-im-assembly"),
	(SECTION_FITTING, "FITTING KIT (HARDWARE & COMPONENTS)", "fk-im-fitting"),
	(SECTION_EXTRA, "EXTRA (ACCESSORIES, FINISHES & APPLIANCES)", "fk-im-extra"),
)


def build_installation_manifest_context(project) -> dict[str, Any]:
	"""Build print context for the Installation Manifest PDF on a unit Project."""
	if getattr(project, "project_type", None) == "Site":
		frappe.throw(_("Installation manifest is only available for unit projects."))

	manifest_name = project.get("fk_effective_manifest")
	if not manifest_name:
		frappe.throw(_("Set Effective Manifest on the Unit tab first."))

	if not frappe.db.exists("Manifest", manifest_name):
		frappe.throw(_("Manifest '{0}' was not found.").format(manifest_name))

	manifest = frappe.get_doc("Manifest", manifest_name)
	item_codes = {line.item_code for line in manifest.items if line.item_code}
	item_meta = _item_meta_map(item_codes)

	sections: dict[str, list[dict]] = {
		SECTION_ASSEMBLY: [],
		SECTION_FITTING: [],
		SECTION_EXTRA: [],
	}

	for line in manifest.items:
		if not line.item_code:
			continue

		meta = item_meta.get(line.item_code, {})
		section = _resolve_manifest_section(line)
		if not section:
			continue

		qty = flt(line.qty or 1) or 1
		qty_display = str(int(qty)) if qty == int(qty) else str(qty)
		sections[section].append(
			{
				"item_code": line.item_code,
				"description": meta.get("item_name") or line.item_code,
				"location": (line.room or "").strip(),
				"qty": qty,
				"qty_display": qty_display,
				"expected": _format_expected(qty, section),
			}
		)

	for section_rows in sections.values():
		for index, row in enumerate(section_rows, start=1):
			row["item_no"] = index

	if not any(sections.values()):
		frappe.throw(_("No manifest lines to print."))

	manifest_sections = []
	section_no = 1
	for section_key, label, css_class in SECTION_DEFINITIONS:
		rows = sections[section_key]
		if not rows:
			continue
		manifest_sections.append(
			{
				"title": f"{section_no}. {label}",
				"css_class": css_class,
				"rows": rows,
			}
		)
		section_no += 1

	qr_png = generate_qr_png_bytes(project.name)
	return {
		"project_code": project.name,
		"project_title": project.get("project_name") or project.name,
		"property_unit": _property_unit_label(project),
		"manifest": manifest_name,
		"qr_base64": base64.b64encode(qr_png).decode("ascii"),
		"sections": manifest_sections,
	}


def _item_meta_map(item_codes: set[str]) -> dict[str, dict]:
	if not item_codes:
		return {}

	return {
		row.name: {"item_name": row.item_name}
		for row in frappe.get_all(
			"Item",
			filters={"name": ["in", list(item_codes)]},
			fields=["name", "item_name"],
		)
	}


def _resolve_manifest_section(line) -> str | None:
	category = (line.label_category or "").strip()
	if not category:
		category = resolve_label_category(line.item_code, line.linked_bom)

	if category == LABEL_CATEGORY_EXTRA:
		return SECTION_EXTRA
	if category == LABEL_CATEGORY_FITTING:
		return SECTION_FITTING
	if category == LABEL_CATEGORY_ASSEMBLY:
		return SECTION_ASSEMBLY
	return SECTION_FITTING


def _format_expected(qty: float, section: str) -> str:
	if section == SECTION_FITTING and qty <= 0:
		return _("As Req.")
	if qty == int(qty):
		return str(int(qty))
	return str(qty)


def _property_unit_label(project) -> str:
	site_name = ""
	if project.get("fk_parent_project"):
		site_name = frappe.db.get_value("Project", project.fk_parent_project, "project_name") or ""

	house = (project.get("fk_house_number") or "").strip()
	if site_name and house:
		return f"{site_name} | {format_unit_location_label(house)}"
	if project.get("project_name"):
		return project.project_name
	return project.name
