# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe

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
from fitzgerald_kitchens.workbook_import.spec_field_map import field_for_spec_label, is_spec_section_label
from fitzgerald_kitchens.workbook_import.workbook_reader import WorkbookReader

SPEC_SHEET = "Spec Sheet"


def import_spec_configurations(
	*,
	reader: WorkbookReader,
	scopes: list[SiteTypeScope],
	quantity_rows: list[dict[str, Any]],
	unit_types: set[str],
	stats: ImportRunStats,
) -> None:
	if not reader.has_sheet(SPEC_SHEET):
		frappe.throw(frappe._("Sheet '{0}' is required.").format(SPEC_SHEET))

	rows = reader.get_sheet_rows(SPEC_SHEET)
	if not rows:
		frappe.throw(frappe._("Spec Sheet is empty."))

	headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
	type_columns = _resolve_type_columns(headers, unit_types)

	for scope in scopes:
		if scope.unit_type not in unit_types:
			continue

		col_idx = type_columns.get(scope.unit_type)
		if col_idx is None:
			frappe.throw(
				frappe._("Spec Sheet is missing column for type {0}.").format(scope.unit_type)
			)

		field_values = _extract_spec_values_for_column(rows, col_idx)
		config_code = build_configuration_code(scope.unit_type, scope.site_name)
		required_kinds = requirements_for_scope(
			quantity_rows, scope.site_name, scope.unit_type
		)

		values = {
			"configuration_name": build_configuration_display_name(
				scope.unit_type, scope.site_name
			),
			"scope": "Project Template",
			**field_values,
		}

		if MANIFEST_KIND_KITCHEN in required_kinds:
			values["kitchen_utility_manifest"] = build_kitchen_manifest_code(
				scope.unit_type, scope.site_name
			)
		if MANIFEST_KIND_ROBE in required_kinds:
			values["wardrobe_manifest"] = build_robe_manifest_code(
				scope.unit_type, scope.site_name
			)
		if MANIFEST_KIND_VANITY in required_kinds:
			values["vanity_unit_manifest"] = build_vanity_manifest_code(
				scope.unit_type, scope.site_name
			)
		if MANIFEST_KIND_PANTRY in required_kinds:
			values["pantry_manifest"] = build_pantry_manifest_code(
				scope.unit_type, scope.site_name
			)

		if frappe.db.exists("Project Unit Configuration", config_code):
			frappe.db.set_value(
				"Project Unit Configuration", config_code, values, update_modified=True
			)
			stats.configurations_updated += 1
			action = "Updated"
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Project Unit Configuration",
					"configuration_code": config_code,
					**values,
				}
			)
			doc.insert(ignore_permissions=True)
			stats.configurations_created += 1
			action = "Created"

		stats.log.append(
			WorkbookImportLogEntry(
				phase="Phase 2",
				document_type="Project Unit Configuration",
				document_code=config_code,
				action=action,
				message=f"{len(field_values)} spec field(s) applied.",
			)
		)


def _resolve_type_columns(headers: list[str], unit_types: set[str]) -> dict[str, int]:
	columns: dict[str, int] = {}
	needed = set(unit_types)

	for idx, header in enumerate(headers):
		header = (header or "").strip()
		if header in needed:
			columns[header] = idx

	return columns


def _extract_spec_values_for_column(rows: list, col_idx: int) -> dict[str, str]:
	values: dict[str, str] = {}

	for row in rows[1:]:
		if col_idx >= len(row):
			continue
		label = str(row[0]).strip() if row[0] is not None else ""
		if not label or is_spec_section_label(label):
			continue

		fieldname = field_for_spec_label(label)
		if not fieldname:
			continue

		cell = row[col_idx]
		if cell is None:
			continue
		text = str(cell).strip()
		if text:
			values[fieldname] = text

	return values
