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

# PUC field that stores the effective manifest code for each manifest kind.
_MANIFEST_FIELD_BY_KIND = {
	MANIFEST_KIND_KITCHEN: "kitchen_utility_manifest",
	MANIFEST_KIND_ROBE: "wardrobe_manifest",
	MANIFEST_KIND_VANITY: "vanity_unit_manifest",
	MANIFEST_KIND_PANTRY: "pantry_manifest",
}

# Manifest sheet attribute + code builder for each manifest kind.
_MANIFEST_SHEET_ATTR_BY_KIND = {
	MANIFEST_KIND_KITCHEN: "kitchen_manifest_sheet",
	MANIFEST_KIND_ROBE: "robe_manifest_sheet",
	MANIFEST_KIND_VANITY: "vanity_manifest_sheet",
	MANIFEST_KIND_PANTRY: "pantry_manifest_sheet",
}
_MANIFEST_CODE_BUILDER_BY_KIND = {
	MANIFEST_KIND_KITCHEN: build_kitchen_manifest_code,
	MANIFEST_KIND_ROBE: build_robe_manifest_code,
	MANIFEST_KIND_VANITY: build_vanity_manifest_code,
	MANIFEST_KIND_PANTRY: build_pantry_manifest_code,
}


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


def validate_manifest_items(
	*,
	reader: WorkbookReader,
	scopes: list[SiteTypeScope],
	quantity_rows: list[dict[str, Any]],
	manifest_mappings: dict[str, TypeManifestSheets],
) -> list[str]:
	"""Pre-import check: does every required manifest sheet have at least one valid Item?

	Mirrors the Phase 1 rule that a Manifest is only created when it has at least
	one row with an Item that exists in ERPNext. Catching this at Validate time
	surfaces missing Items before the import ever links a Project Unit Configuration
	to a Manifest that will never be created.
	"""
	errors: list[str] = []
	sheet_item_cache: dict[str, bool] = {}

	def _sheet_has_valid_item(sheet_name: str) -> bool:
		if sheet_name not in sheet_item_cache:
			has_item = False
			for row in reader.get_sheet_as_dicts(sheet_name):
				item_code = _get_row_value(row, "Description", "description")
				if item_code and frappe.db.exists("Item", item_code):
					has_item = True
					break
			sheet_item_cache[sheet_name] = has_item
		return sheet_item_cache[sheet_name]

	for scope in scopes:
		type_sheets = manifest_mappings.get(scope.unit_type)
		if not type_sheets:
			continue

		required_kinds = requirements_for_scope(quantity_rows, scope.site_name, scope.unit_type)
		if not required_kinds:
			continue

		mapping_row = type_sheets.as_mapping_row()
		for kind, sheet_attr in _MANIFEST_SHEET_ATTR_BY_KIND.items():
			if kind not in required_kinds:
				continue
			sheet_name = getattr(mapping_row, sheet_attr, "")
			if not sheet_name or _sheet_has_valid_item(sheet_name):
				continue
			manifest_code = _MANIFEST_CODE_BUILDER_BY_KIND[kind](scope.unit_type, scope.site_name)
			errors.append(
				f"No valid Items found on sheet '{sheet_name}' for manifest {manifest_code} "
				f"({scope.unit_type} / {scope.site_name}). Every row's Item code (Description "
				f"column) is missing from this site's Item list, so the Manifest will not be "
				f"created and the import will fail. Create these Items before importing."
			)

	return errors


def validate_manifest_links(
	scopes: list[SiteTypeScope], quantity_rows: list[dict[str, Any]]
) -> list[str]:
	"""Fail-fast check: does every manifest a PUC now links to actually exist?

	Phase 2 always stamps the expected manifest code onto the Project Unit
	Configuration, even when Phase 1 skipped creating that Manifest (e.g. every
	row's Item was missing on this site). Left unchecked, Phase 3 only surfaces
	this deep inside Project creation as a confusing "Could not find Effective
	Manifest" error, after part of the import has already happened.
	"""
	errors: list[str] = []
	for scope in scopes:
		required_kinds = requirements_for_scope(quantity_rows, scope.site_name, scope.unit_type)
		if not required_kinds:
			continue

		config_code = build_configuration_code(scope.unit_type, scope.site_name)
		puc_fields = frappe.db.get_value(
			"Project Unit Configuration",
			config_code,
			list(_MANIFEST_FIELD_BY_KIND.values()),
			as_dict=True,
		)
		if not puc_fields:
			continue

		for kind, field_name in _MANIFEST_FIELD_BY_KIND.items():
			if kind not in required_kinds:
				continue
			manifest_code = puc_fields.get(field_name)
			if manifest_code and not frappe.db.exists("Manifest", manifest_code):
				errors.append(
					f"Configuration {config_code} expects {field_name} = '{manifest_code}', "
					f"but that Manifest was never created. Check the Phase 1 import log for "
					f"missing Items on the related manifest sheet."
				)

	return errors


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
