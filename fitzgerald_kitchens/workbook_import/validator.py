# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe

from fitzgerald_kitchens.workbook_import.constants import (
	QTY_COLUMNS,
	SUB_UNIT_PROJECT_QTY_COLUMNS,
	has_kitchen_unit,
)
from fitzgerald_kitchens.workbook_import.scope import collect_site_type_scopes, count_unique_sites


def validate_workbook_rows(
	rows: list[dict[str, Any]],
	*,
	create_missing_developer: bool,
	validate_configuration_exists: bool = True,
) -> tuple[list[str], dict[str, int]]:
	"""Return validation errors and preview counts."""
	errors: list[str] = []
	sites: set[tuple[str, str]] = set()
	expected_units = 0

	for row in rows:
		row_label = _row_label(row)
		developer = (row.get("developer") or "").strip()
		row["developer"] = developer
		site_name = row.get("site_name")
		house_number = row.get("house_number")
		config_code = row.get("configuration_code")

		if not developer:
			errors.append(f"{row_label}: Developer is required.")
		elif not _developer_exists(developer) and not create_missing_developer:
			errors.append(f"{row_label}: Customer '{developer}' not found.")

		if not site_name:
			errors.append(f"{row_label}: Name (site) is required.")

		if house_number in (None, ""):
			errors.append(f"{row_label}: Number (plot) is required.")

		if not config_code:
			errors.append(f"{row_label}: Type is required.")
		elif validate_configuration_exists and not frappe.db.exists(
			"Project Unit Configuration", config_code
		):
			errors.append(
				f"{row_label}: Project Unit Configuration '{config_code}' not found."
			)

		qtys = _parse_qty_columns(row, row_label, errors)
		if not any(qtys.values()):
			errors.append(f"{row_label}: At least one unit quantity must be greater than zero.")

		if any(qtys[col] > 0 for col, _ptype in SUB_UNIT_PROJECT_QTY_COLUMNS) and not has_kitchen_unit(
			qtys
		):
			errors.append(
				f"{row_label}: Kitchen quantity must be greater than zero when other unit types are requested."
			)

		if developer and site_name:
			sites.add((developer, site_name))

		if has_kitchen_unit(qtys):
			expected_units += 1
		for col, _project_type in SUB_UNIT_PROJECT_QTY_COLUMNS:
			if qtys[col] > 0:
				expected_units += 1

	preview = {
		"plot_count": len(rows),
		"site_count": count_unique_sites(rows),
		"unit_project_count": expected_units,
		"configuration_count": len(collect_site_type_scopes(rows)),
	}
	return errors, preview


def _parse_qty_columns(row: dict[str, Any], row_label: str, errors: list[str]) -> dict[str, int]:
	qtys: dict[str, int] = {}
	for col, _project_type in QTY_COLUMNS:
		raw = row.get(col, 0)
		if raw in (None, ""):
			qtys[col] = 0
			continue
		try:
			value = int(float(str(raw).strip()))
		except (TypeError, ValueError):
			errors.append(f"{row_label}: Invalid quantity for {_column_label(col)}.")
			value = 0
		if value < 0:
			errors.append(f"{row_label}: {_column_label(col)} cannot be negative.")
			value = 0
		qtys[col] = value
	return qtys


def _developer_exists(developer: str) -> bool:
	if frappe.db.exists("Customer", developer):
		return True
	return bool(frappe.db.exists("Customer", {"customer_name": developer}))


def _row_label(row: dict[str, Any]) -> str:
	return f"Row {row.get('row_number', '?')}"


def _column_label(column: str) -> str:
	return column.replace("_qty", "").replace("_", " ").title()
