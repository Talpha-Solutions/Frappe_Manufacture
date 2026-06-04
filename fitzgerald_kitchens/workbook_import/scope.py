# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fitzgerald_kitchens.workbook_import.type_mapping import TypeMappingRow


@dataclass(frozen=True)
class SiteTypeScope:
	site_name: str
	unit_type: str


def collect_site_type_scopes(rows: list[dict[str, Any]]) -> list[SiteTypeScope]:
	seen: set[tuple[str, str]] = set()
	scopes: list[SiteTypeScope] = []

	for row in rows:
		site_name = (row.get("site_name") or "").strip()
		unit_type = _row_unit_type(row)
		if not site_name or not unit_type:
			continue
		key = (site_name, unit_type)
		if key in seen:
			continue
		seen.add(key)
		scopes.append(SiteTypeScope(site_name=site_name, unit_type=unit_type))

	return scopes


def mapping_by_type(type_mappings: list[TypeMappingRow]) -> dict[str, TypeMappingRow]:
	return {mapping.unit_type: mapping for mapping in type_mappings}


def count_unique_sites(rows: list[dict[str, Any]]) -> int:
	return len(
		{
			(row.get("site_name") or "").strip()
			for row in rows
			if (row.get("site_name") or "").strip()
		}
	)


def _row_unit_type(row: dict[str, Any]) -> str:
	raw = (row.get("_unit_type") or row.get("configuration_code") or "").strip()
	if not raw:
		return ""
	if row.get("_unit_type"):
		return raw
	if "-" in raw:
		return raw.split("-", 1)[0].strip()
	return raw
