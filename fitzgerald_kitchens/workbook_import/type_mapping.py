# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass, field

from fitzgerald_kitchens.workbook_import.manifest_kinds import (
	MANIFEST_KIND_KITCHEN,
	MANIFEST_KIND_PANTRY,
	MANIFEST_KIND_ROBE,
	MANIFEST_KIND_VANITY,
)
from fitzgerald_kitchens.workbook_import.workbook_reader import WorkbookReader

# Match longest manifest suffixes first when scanning tab names.
MANIFEST_SUFFIXES: tuple[tuple[str, str], ...] = (
	(" Robe Manifest", MANIFEST_KIND_ROBE),
	(" Vanity Unit Manifest", MANIFEST_KIND_VANITY),
	(" Vanity Manifest", MANIFEST_KIND_VANITY),
	(" Pantry Manifest", MANIFEST_KIND_PANTRY),
	(" Manifest", MANIFEST_KIND_KITCHEN),
)

EXPECTED_SHEET_BY_KIND: dict[str, str] = {
	MANIFEST_KIND_KITCHEN: " Manifest",
	MANIFEST_KIND_ROBE: " Robe Manifest",
	MANIFEST_KIND_VANITY: " Vanity Unit Manifest",
	MANIFEST_KIND_PANTRY: " Pantry Manifest",
}

RESERVED_SHEETS = frozenset(
	{
		"Quantity Sheet",
		"Spec Sheet",
		"Type Mapping",
		"Demo Delivery Schedule",
		"Task Schedule Template",
		"Manifest Summary",
		"Demo Summary",
	}
)


@dataclass(frozen=True)
class TypeMappingRow:
	"""Manifest sheet names discovered for one apartment type."""

	unit_type: str
	kitchen_manifest_sheet: str = ""
	robe_manifest_sheet: str = ""
	vanity_manifest_sheet: str = ""
	pantry_manifest_sheet: str = ""


@dataclass
class TypeManifestSheets:
	unit_type: str
	sheets: dict[str, str] = field(default_factory=dict)

	def get(self, kind: str) -> str | None:
		return self.sheets.get(kind)

	@property
	def kitchen_manifest_sheet(self) -> str:
		return self.sheets.get(MANIFEST_KIND_KITCHEN, "")

	@property
	def robe_manifest_sheet(self) -> str:
		return self.sheets.get(MANIFEST_KIND_ROBE, "")

	def as_mapping_row(self) -> TypeMappingRow:
		return TypeMappingRow(
			unit_type=self.unit_type,
			kitchen_manifest_sheet=self.kitchen_manifest_sheet,
			robe_manifest_sheet=self.robe_manifest_sheet,
			vanity_manifest_sheet=self.sheets.get(MANIFEST_KIND_VANITY, ""),
			pantry_manifest_sheet=self.sheets.get(MANIFEST_KIND_PANTRY, ""),
		)


def discover_manifest_sheet_mappings(reader: WorkbookReader) -> dict[str, TypeManifestSheets]:
	"""Discover manifest tabs by naming convention."""
	by_type: dict[str, dict[str, str]] = {}

	for sheet_name in reader.sheet_names():
		if sheet_name in RESERVED_SHEETS:
			continue

		for suffix, kind in MANIFEST_SUFFIXES:
			if not sheet_name.endswith(suffix):
				continue
			unit_type = sheet_name[: -len(suffix)].strip()
			if not unit_type:
				break
			type_sheets = by_type.setdefault(unit_type, {})
			if kind not in type_sheets:
				type_sheets[kind] = sheet_name
			break

	return {
		unit_type: TypeManifestSheets(unit_type=unit_type, sheets=sheets)
		for unit_type, sheets in sorted(by_type.items())
	}


def expected_manifest_sheet_name(unit_type: str, kind: str) -> str:
	suffix = EXPECTED_SHEET_BY_KIND.get(kind, "")
	return f"{(unit_type or '').strip()}{suffix}"


def validation_errors_for_manifest_sheets(
	discovered: dict[str, TypeManifestSheets],
	required_by_type: dict[str, set[str]],
) -> list[str]:
	errors: list[str] = []

	for unit_type in sorted(required_by_type):
		required_kinds = required_by_type[unit_type]
		type_sheets = discovered.get(unit_type)

		for kind in sorted(required_kinds):
			if type_sheets and type_sheets.get(kind):
				continue
			errors.append(
				f"Type '{unit_type}' requires workbook tab '{expected_manifest_sheet_name(unit_type, kind)}'."
			)

	return errors
