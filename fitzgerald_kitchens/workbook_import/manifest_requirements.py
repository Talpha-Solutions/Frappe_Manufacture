# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fitzgerald_kitchens.workbook_import.constants import needs_kitchen_utility_manifest
from fitzgerald_kitchens.workbook_import.manifest_kinds import (
	MANIFEST_KIND_KITCHEN,
	MANIFEST_KIND_PANTRY,
	MANIFEST_KIND_ROBE,
	MANIFEST_KIND_VANITY,
)
from fitzgerald_kitchens.workbook_import.qty_rows import parse_row_qtys

QTY_COLUMN_TO_MANIFEST_KIND = {
	"robe_qty": MANIFEST_KIND_ROBE,
	"vanity_qty": MANIFEST_KIND_VANITY,
	"pantry_qty": MANIFEST_KIND_PANTRY,
}


def manifest_kinds_for_qtys(qtys: dict[str, int]) -> set[str]:
	kinds: set[str] = set()
	if needs_kitchen_utility_manifest(qtys):
		kinds.add(MANIFEST_KIND_KITCHEN)
	for qty_col, kind in QTY_COLUMN_TO_MANIFEST_KIND.items():
		if qtys.get(qty_col, 0) > 0:
			kinds.add(kind)
	return kinds


def _row_unit_type(row: dict[str, Any]) -> str:
	raw = (row.get("_unit_type") or row.get("configuration_code") or "").strip()
	if not raw:
		return ""
	if row.get("_unit_type"):
		return raw
	if "-" in raw:
		return raw.split("-", 1)[0].strip()
	return raw


def requirements_by_type(quantity_rows: list[dict[str, Any]]) -> dict[str, set[str]]:
	required: dict[str, set[str]] = defaultdict(set)
	for row in quantity_rows:
		unit_type = _row_unit_type(row)
		if not unit_type:
			continue
		required[unit_type] |= manifest_kinds_for_qtys(parse_row_qtys(row))
	return dict(required)


def requirements_for_scope(
	quantity_rows: list[dict[str, Any]],
	site_name: str,
	unit_type: str,
) -> set[str]:
	site_name = (site_name or "").strip()
	unit_type = (unit_type or "").strip()
	kinds: set[str] = set()

	for row in quantity_rows:
		if (row.get("site_name") or "").strip() != site_name:
			continue
		if _row_unit_type(row) != unit_type:
			continue
		kinds |= manifest_kinds_for_qtys(parse_row_qtys(row))

	return kinds


def count_planned_manifests(
	quantity_rows: list[dict[str, Any]],
	scopes,
) -> int:
	total = 0
	seen: set[tuple[str, str, str]] = set()
	for scope in scopes:
		for kind in requirements_for_scope(quantity_rows, scope.site_name, scope.unit_type):
			key = (scope.site_name, scope.unit_type, kind)
			if key in seen:
				continue
			seen.add(key)
			total += 1
	return total
