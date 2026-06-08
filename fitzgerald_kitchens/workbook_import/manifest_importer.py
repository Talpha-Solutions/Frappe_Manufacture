# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

from fitzgerald_kitchens.workbook_import.import_log import ImportRunStats, WorkbookImportLogEntry
from fitzgerald_kitchens.workbook_import.manifest_kinds import (
	MANIFEST_KIND_KITCHEN,
	MANIFEST_KIND_PANTRY,
	MANIFEST_KIND_ROBE,
	MANIFEST_KIND_VANITY,
)
from fitzgerald_kitchens.workbook_import.manifest_requirements import requirements_for_scope
from fitzgerald_kitchens.workbook_import.naming import (
	build_configuration_code,
	build_configuration_display_name,
	build_kitchen_manifest_code,
	build_pantry_manifest_code,
	build_robe_manifest_code,
	build_vanity_manifest_code,
)
from fitzgerald_kitchens.workbook_import.scope import SiteTypeScope
from fitzgerald_kitchens.setup.manifest_line_labels import (
	resolve_label_category,
	resolve_manifest_linked_bom,
)
from fitzgerald_kitchens.workbook_import.type_mapping import TypeManifestSheets
from fitzgerald_kitchens.workbook_import.workbook_reader import WorkbookReader


def ensure_configuration_stubs(scopes: list[SiteTypeScope], stats: ImportRunStats) -> None:
	for scope in scopes:
		code = build_configuration_code(scope.unit_type, scope.site_name)
		if frappe.db.exists("Project Unit Configuration", code):
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Project Unit Configuration",
				"configuration_code": code,
				"configuration_name": build_configuration_display_name(
					scope.unit_type, scope.site_name
				),
				"scope": "Project Template",
			}
		)
		doc.insert(ignore_permissions=True)
		stats.configurations_created += 1
		stats.log.append(
			WorkbookImportLogEntry(
				phase="Phase 0",
				document_type="Project Unit Configuration",
				document_code=code,
				action="Created",
				message="Configuration stub for manifest import.",
			)
		)


def import_manifests(
	*,
	reader: WorkbookReader,
	scopes: list[SiteTypeScope],
	quantity_rows: list[dict[str, Any]],
	manifest_mappings: dict[str, TypeManifestSheets],
	strict_item_validation: bool,
	stats: ImportRunStats,
) -> None:
	for scope in scopes:
		type_sheets = manifest_mappings.get(scope.unit_type)
		if not type_sheets:
			continue

		required_kinds = requirements_for_scope(
			quantity_rows, scope.site_name, scope.unit_type
		)
		if not required_kinds:
			continue

		config_code = build_configuration_code(scope.unit_type, scope.site_name)
		mapping_row = type_sheets.as_mapping_row()

		if MANIFEST_KIND_KITCHEN in required_kinds and mapping_row.kitchen_manifest_sheet:
			_import_manifest_sheet(
				reader=reader,
				sheet_name=mapping_row.kitchen_manifest_sheet,
				manifest_code=build_kitchen_manifest_code(scope.unit_type, scope.site_name),
				configuration_code=config_code,
				manifest_category="Kitchen",
				strict_item_validation=strict_item_validation,
				stats=stats,
			)

		if MANIFEST_KIND_ROBE in required_kinds and mapping_row.robe_manifest_sheet:
			_import_manifest_sheet(
				reader=reader,
				sheet_name=mapping_row.robe_manifest_sheet,
				manifest_code=build_robe_manifest_code(scope.unit_type, scope.site_name),
				configuration_code=config_code,
				manifest_category="Robe",
				strict_item_validation=strict_item_validation,
				stats=stats,
			)

		if MANIFEST_KIND_VANITY in required_kinds and mapping_row.vanity_manifest_sheet:
			_import_manifest_sheet(
				reader=reader,
				sheet_name=mapping_row.vanity_manifest_sheet,
				manifest_code=build_vanity_manifest_code(scope.unit_type, scope.site_name),
				configuration_code=config_code,
				manifest_category="Vanity",
				strict_item_validation=strict_item_validation,
				stats=stats,
			)

		if MANIFEST_KIND_PANTRY in required_kinds and mapping_row.pantry_manifest_sheet:
			_import_manifest_sheet(
				reader=reader,
				sheet_name=mapping_row.pantry_manifest_sheet,
				manifest_code=build_pantry_manifest_code(scope.unit_type, scope.site_name),
				configuration_code=config_code,
				manifest_category="Pantry",
				strict_item_validation=strict_item_validation,
				stats=stats,
			)


def _import_manifest_sheet(
	*,
	reader: WorkbookReader,
	sheet_name: str,
	manifest_code: str,
	configuration_code: str,
	manifest_category: str,
	strict_item_validation: bool,
	stats: ImportRunStats,
) -> None:
	rows = reader.get_sheet_as_dicts(sheet_name)
	items = _build_manifest_items(rows, strict_item_validation, stats, sheet_name)

	if not items:
		stats.log.append(
			WorkbookImportLogEntry(
				phase="Phase 1",
				document_type="Manifest",
				document_code=manifest_code,
				action="Failed",
				message=f"No valid items on sheet {sheet_name}.",
			)
		)
		return

	if frappe.db.exists("Manifest", manifest_code):
		doc = frappe.get_doc("Manifest", manifest_code)
		doc.items = []
		for item in items:
			doc.append("items", item)
		doc.configuration = configuration_code
		doc.manifest_category = manifest_category
		doc.save(ignore_permissions=True)
		stats.manifests_updated += 1
		action = "Updated"
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Manifest",
				"manifest_code": manifest_code,
				"scope": "Project Template",
				"manifest_category": manifest_category,
				"configuration": configuration_code,
				"items": items,
			}
		)
		doc.insert(ignore_permissions=True)
		stats.manifests_created += 1
		action = "Created"

	stats.log.append(
		WorkbookImportLogEntry(
			phase="Phase 1",
			document_type="Manifest",
			document_code=manifest_code,
			action=action,
			message=f"{len(items)} item(s) from {sheet_name}.",
		)
	)


def _build_manifest_items(
	rows: list[dict[str, Any]],
	strict_item_validation: bool,
	stats: ImportRunStats,
	sheet_name: str,
) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []

	for row in rows:
		item_code = _get_row_value(row, "Description", "description")
		if not item_code:
			continue

		if not frappe.db.exists("Item", item_code):
			message = f"Item '{item_code}' not found (sheet {sheet_name}, row {row.get('row_number')})."
			if strict_item_validation:
				stats.log.append(
					WorkbookImportLogEntry(
						phase="Phase 1",
						document_type="Manifest Item",
						document_code=item_code,
						action="Failed",
						row_number=int(row.get("row_number") or 0),
						message=message,
					)
				)
				continue
			stats.log.append(
				WorkbookImportLogEntry(
					phase="Phase 1",
					document_type="Manifest Item",
					document_code=item_code,
					action="Skipped",
					row_number=int(row.get("row_number") or 0),
					message=message,
				)
			)
			continue

		qty = flt(_get_row_value(row, "Qty", "qty") or 1) or 1
		linked_bom = resolve_manifest_linked_bom(item_code)
		items.append(
			{
				"item_code": item_code,
				"description": _get_row_value(row, "Item Description", "item description") or None,
				"qty": qty,
				"width": _float_or_none(_get_row_value(row, "Width", "width")),
				"height": _float_or_none(_get_row_value(row, "Height", "height")),
				"depth": _float_or_none(_get_row_value(row, "Depth", "depth")),
				"room": _get_row_value(row, "Room", "room") or None,
				"linked_bom": linked_bom,
				"label_category": resolve_label_category(item_code, linked_bom),
			}
		)

	return items


def _get_row_value(row: dict, *keys: str) -> str:
	for key in keys:
		if key in row and str(row[key]).strip():
			return str(row[key]).strip()
		lower = key.lower()
		for header, value in row.items():
			if str(header).strip().lower() == lower and str(value or "").strip():
				return str(value).strip()
	return ""


def _float_or_none(value: str) -> float | None:
	if not value:
		return None
	try:
		return flt(value)
	except (TypeError, ValueError):
		return None
