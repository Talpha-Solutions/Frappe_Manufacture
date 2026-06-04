# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass

import frappe

from fitzgerald_kitchens.workbook_import.parser import WorkbookParseError
from fitzgerald_kitchens.workbook_import.workbook_reader import WorkbookReader

TYPE_MAPPING_SHEET = "Type Mapping"


@dataclass
class TypeMappingRow:
	unit_type: str
	kitchen_manifest_sheet: str
	robe_manifest_sheet: str


def parse_type_mapping(reader: WorkbookReader) -> list[TypeMappingRow]:
	if not reader.has_sheet(TYPE_MAPPING_SHEET):
		raise WorkbookParseError(frappe._("Sheet '{0}' is required.").format(TYPE_MAPPING_SHEET))

	rows = reader.get_sheet_as_dicts(TYPE_MAPPING_SHEET)
	mappings: list[TypeMappingRow] = []

	for row in rows:
		unit_type = _get_cell(row, "Type", "type")
		if not unit_type:
			continue

		kitchen_sheet = _get_cell(row, "Kitchen Manifest Sheet", "kitchen manifest sheet")
		robe_sheet = _get_cell(row, "Robe Manifest Sheet", "robe manifest sheet")
		if not kitchen_sheet or not robe_sheet:
			raise WorkbookParseError(
				frappe._("Type Mapping row for {0} must include kitchen and robe manifest sheets.").format(
					unit_type
				)
			)

		mappings.append(
			TypeMappingRow(
				unit_type=unit_type,
				kitchen_manifest_sheet=kitchen_sheet,
				robe_manifest_sheet=robe_sheet,
			)
		)

	if not mappings:
		raise WorkbookParseError(frappe._("Type Mapping sheet has no type rows."))

	return mappings


def _get_cell(row: dict, *keys: str) -> str:
	for key in keys:
		if key in row and str(row[key]).strip():
			return str(row[key]).strip()
		lower = key.lower()
		for header, value in row.items():
			if str(header).strip().lower() == lower and str(value).strip():
				return str(value).strip()
	return ""
