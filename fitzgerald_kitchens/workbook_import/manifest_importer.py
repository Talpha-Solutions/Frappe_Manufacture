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
	# Shared across every sheet/scope in this run so a repeated Item code (the
	# common case — the same cabinet appears on many manifest rows) is only
	# looked up / created / logged once, however many times it recurs.
	item_cache: dict[str, dict[str, Any]] = {}

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
				item_cache=item_cache,
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
				item_cache=item_cache,
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
				item_cache=item_cache,
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
				item_cache=item_cache,
			)


def preview_manifest_sheets(
	*,
	reader: WorkbookReader,
	scopes: list[SiteTypeScope],
	quantity_rows: list[dict[str, Any]],
	manifest_mappings: dict[str, TypeManifestSheets],
	strict_item_validation: bool = False,
) -> tuple[list[str], dict[str, Any]]:
	"""Read-only Phase 1 preview across every required Manifest sheet.

	Only performs `exists()`/`get_value()` reads — no Item or Manifest is created
	or modified here. Returns (blocking_errors, preview) where `preview` reports
	the counts requested for the Validate step, and `blocking_errors` only
	contains failures that would stop the whole import (currently: a required
	sheet has zero usable rows while Strict Item Validation is enabled).
	"""
	errors: list[str] = []
	sheets_seen: set[str] = set()
	total_rows = 0
	invalid_rows = 0
	unique_item_codes: set[str] = set()
	item_descriptions: dict[str, set[str]] = {}
	existing_items: set[str] = set()
	missing_items: set[str] = set()
	manifests_to_create: set[str] = set()
	manifests_to_update: set[str] = set()

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
			if not sheet_name:
				continue
			sheets_seen.add(sheet_name)

			manifest_code = _MANIFEST_CODE_BUILDER_BY_KIND[kind](scope.unit_type, scope.site_name)
			sheet_has_usable_row = False

			for row in reader.get_sheet_as_dicts(sheet_name):
				if not _row_has_any_data(row):
					continue  # blank padding row — not a data row

				item_code = _get_row_value(row, "Description", "description")
				if not item_code:
					invalid_rows += 1
					continue

				total_rows += 1
				unique_item_codes.add(item_code)
				item_description = _get_row_value(row, "Item Description", "item description")
				if item_description:
					item_descriptions.setdefault(item_code, set()).add(item_description)

				if frappe.db.exists("Item", item_code):
					existing_items.add(item_code)
					sheet_has_usable_row = True
				else:
					missing_items.add(item_code)
					if not strict_item_validation:
						sheet_has_usable_row = True

			if not sheet_has_usable_row:
				if strict_item_validation:
					errors.append(
						f"No valid Items found on sheet '{sheet_name}' for manifest {manifest_code} "
						f"({scope.unit_type} / {scope.site_name}). Every row's Item code "
						f"(Description column) is missing from this site's Item list, and Strict "
						f"Item Validation is enabled, so the Manifest will not be created. Create "
						f"these Items before importing, or disable Strict Item Validation to "
						f"auto-create them from the workbook."
					)
				continue

			if frappe.db.exists("Manifest", manifest_code):
				manifests_to_update.add(manifest_code)
			else:
				manifests_to_create.add(manifest_code)

	items_to_create = set() if strict_item_validation else set(missing_items)
	items_to_update = {
		code
		for code in existing_items
		if item_descriptions.get(code)
		and not (frappe.db.get_value("Item", code, "description") or "").strip()
	}
	conflicting_items = {
		code: sorted(descriptions)
		for code, descriptions in item_descriptions.items()
		if len(descriptions) > 1
	}

	preview = {
		"manifest_sheets_found": sorted(sheets_seen),
		"manifest_sheet_count": len(sheets_seen),
		"total_manifest_rows": total_rows,
		"unique_item_codes": len(unique_item_codes),
		"existing_items": len(existing_items),
		"missing_items": len(missing_items),
		"items_to_create": len(items_to_create),
		"items_to_update": len(items_to_update),
		"conflicting_items": conflicting_items,
		"invalid_rows": invalid_rows,
		"manifests_to_create": len(manifests_to_create),
		"manifests_to_update": len(manifests_to_update),
	}

	return errors, preview


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
	item_cache: dict[str, dict[str, Any]],
) -> None:
	rows = reader.get_sheet_as_dicts(sheet_name)
	items = _build_manifest_items(rows, strict_item_validation, stats, sheet_name, item_cache)

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
	item_cache: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []

	for row in rows:
		row_number = int(row.get("row_number") or 0)
		item_code = _get_row_value(row, "Description", "description")
		if not item_code:
			if _row_has_any_data(row):
				stats.log.append(
					WorkbookImportLogEntry(
						phase="Phase 1",
						document_type="Manifest Item",
						document_code="",
						action="Failed",
						row_number=row_number,
						message=f"Blank Item Code (Description column) on sheet {sheet_name}.",
					)
				)
			continue

		item_description = _get_row_value(row, "Item Description", "item description")
		if not _upsert_item(
			item_code=item_code,
			item_description=item_description,
			create_missing=not strict_item_validation,
			stats=stats,
			sheet_name=sheet_name,
			row_number=row_number,
			item_cache=item_cache,
		):
			continue

		qty = flt(_get_row_value(row, "Qty", "qty") or 1) or 1
		linked_bom = resolve_manifest_linked_bom(item_code)
		items.append(
			{
				"item_code": item_code,
				"description": item_description or None,
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


def _row_has_any_data(row: dict[str, Any]) -> bool:
	for key, value in row.items():
		if key == "row_number":
			continue
		if str(value or "").strip():
			return True
	return False


def _upsert_item(
	*,
	item_code: str,
	item_description: str,
	create_missing: bool,
	stats: ImportRunStats,
	sheet_name: str,
	row_number: int,
	item_cache: dict[str, dict[str, Any]],
) -> bool:
	"""Ensure `item_code` exists as an Item, auto-creating it from the workbook row if missing.

	Each item_code is only resolved (looked up / created) once per import run —
	item_cache remembers the outcome — even though the same cabinet/component
	typically appears on many manifest rows across several sheets (e.g. B60 on
	T1/T1V/T2/T3 Manifest). Returns True if the Manifest line should include
	this item.

	Dimensions (width/height/depth) are never written here — they belong to the
	Manifest Item child row the caller builds, not the Item master, so a
	different width for the same item_code on another sheet (e.g. Robe Top
	Panel) cannot corrupt shared Item data. A differing Item Description text
	for an already-resolved code is only reported as a Conflict log entry —
	the Item master keeps whatever description it was first resolved with.
	"""
	cached = item_cache.get(item_code)
	if cached is not None:
		if (
			item_description
			and cached.get("description")
			and item_description != cached["description"]
		):
			stats.log.append(
				WorkbookImportLogEntry(
					phase="Phase 1",
					document_type="Item",
					document_code=item_code,
					action="Conflict",
					row_number=row_number,
					message=(
						f"Sheet {sheet_name} lists Item Description '{item_description}' for "
						f"{item_code}, but '{cached['description']}' was already used to resolve "
						f"this Item earlier in the import. The Item master is unchanged; only the "
						f"first description encountered is used."
					),
				)
			)
		return cached["ok"]

	if frappe.db.exists("Item", item_code):
		changed = _backfill_item_description_if_blank(item_code, item_description)
		action = "Updated" if changed else "Reused"
		if changed:
			stats.items_updated += 1
		item_cache[item_code] = {"ok": True, "description": item_description or None}
		stats.log.append(
			WorkbookImportLogEntry(
				phase="Phase 1",
				document_type="Item",
				document_code=item_code,
				action=action,
				row_number=row_number,
				message=f"Matched existing Item from sheet {sheet_name}.",
			)
		)
		return True

	if not create_missing:
		item_cache[item_code] = {"ok": False, "description": item_description or None}
		stats.items_skipped += 1
		stats.log.append(
			WorkbookImportLogEntry(
				phase="Phase 1",
				document_type="Item",
				document_code=item_code,
				action="Skipped",
				row_number=row_number,
				message=(
					f"Item '{item_code}' not found (sheet {sheet_name}, row {row_number}). "
					f"Strict Item Validation is enabled so it was not auto-created."
				),
			)
		)
		return False

	savepoint = "manifest_item_upsert"
	frappe.db.savepoint(savepoint)
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": (item_description or item_code)[:140],
				"item_group": _default_item_group(),
				"stock_uom": _default_stock_uom(),
				"is_stock_item": 1,
				"description": item_description or None,
			}
		)
		doc.insert(ignore_permissions=True)
	except Exception as exc:
		frappe.db.rollback(save_point=savepoint)
		item_cache[item_code] = {"ok": False, "description": item_description or None}
		stats.items_errors += 1
		stats.log.append(
			WorkbookImportLogEntry(
				phase="Phase 1",
				document_type="Item",
				document_code=item_code,
				action="Failed",
				row_number=row_number,
				message=f"Could not auto-create Item from sheet {sheet_name}: {exc}",
			)
		)
		return False

	item_cache[item_code] = {"ok": True, "description": item_description or None}
	stats.items_created += 1
	stats.log.append(
		WorkbookImportLogEntry(
			phase="Phase 1",
			document_type="Item",
			document_code=item_code,
			action="Created",
			row_number=row_number,
			message=f"Auto-created from sheet {sheet_name} (Description column = Item Code).",
		)
	)
	return True


def _backfill_item_description_if_blank(item_code: str, item_description: str) -> bool:
	"""Fill in a blank Item.description from the workbook row; never overwrite an existing one."""
	if not item_description:
		return False
	current_description = frappe.db.get_value("Item", item_code, "description")
	if (current_description or "").strip():
		return False
	frappe.db.set_value("Item", item_code, "description", item_description, update_modified=True)
	return True


def _default_item_group() -> str:
	group = frappe.db.get_single_value("Stock Settings", "item_group")
	if group and frappe.db.exists("Item Group", group):
		return group
	return "All Item Groups"


def _default_stock_uom() -> str:
	uom = frappe.db.get_single_value("Stock Settings", "stock_uom")
	if uom and frappe.db.exists("UOM", uom):
		return uom
	return "Nos"


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
