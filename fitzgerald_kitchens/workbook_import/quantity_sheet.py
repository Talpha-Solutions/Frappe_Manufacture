# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe

from fitzgerald_kitchens.workbook_import.constants import COLUMN_ALIASES
from fitzgerald_kitchens.workbook_import.naming import build_configuration_code
from fitzgerald_kitchens.workbook_import.parser import WorkbookParseError, _is_empty_row, _normalize_header
from fitzgerald_kitchens.workbook_import.workbook_reader import WorkbookReader

QUANTITY_SHEET = "Quantity Sheet"
REQUIRED_COLUMNS = (
	"developer",
	"site_name",
	"house_number",
	"configuration_code",
)


def parse_quantity_sheet(reader: WorkbookReader) -> list[dict[str, Any]]:
	if not reader.has_sheet(QUANTITY_SHEET):
		raise WorkbookParseError(frappe._("Sheet '{0}' is required.").format(QUANTITY_SHEET))

	raw_rows = reader.get_sheet_as_dicts(QUANTITY_SHEET)
	rows: list[dict[str, Any]] = []

	for raw in raw_rows:
		if _is_empty_row(raw):
			continue

		normalized: dict[str, Any] = {"row_number": raw.get("row_number")}
		for header, value in raw.items():
			if header == "row_number":
				continue
			key = COLUMN_ALIASES.get(_normalize_header(str(header)))
			if key:
				normalized[key] = str(value).strip() if value is not None else ""

		developer = (normalized.get("developer") or "").strip()
		normalized["developer"] = developer

		unit_type = (normalized.get("configuration_code") or "").strip()
		normalized["_unit_type"] = unit_type
		site_name = (normalized.get("site_name") or "").strip()
		if unit_type and site_name:
			normalized["configuration_code"] = build_configuration_code(unit_type, site_name)

		if not normalized.get("developer") or not site_name:
			continue
		if normalized.get("house_number") in (None, ""):
			continue
		if not unit_type:
			continue

		rows.append(normalized)

	if not rows:
		raise WorkbookParseError(frappe._("Quantity Sheet has no data rows."))

	return rows
