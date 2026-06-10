# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from fitzgerald_kitchens.setup.project_unit_fields import KITCHEN_PROJECT_TYPE, SITE_PROJECT_TYPE

# Spreadsheet column header (lower-case) -> normalized field
COLUMN_ALIASES = {
	"developer": "developer",
	"name": "site_name",
	"number": "house_number",
	"bed no.": "bedrooms",
	"bed no": "bedrooms",
	"bedrooms": "bedrooms",
	"type": "configuration_code",
	"kitchen": "kitchen_qty",
	"robe": "robe_qty",
	"utility": "utility_qty",
	"vanity unit": "vanity_qty",
	"vanity": "vanity_qty",
	"pantry": "pantry_qty",
}

REQUIRED_COLUMNS = (
	"developer",
	"site_name",
	"house_number",
	"configuration_code",
)

# All quantity columns read from the workbook.
QTY_COLUMNS = (
	("kitchen_qty", KITCHEN_PROJECT_TYPE),
	("robe_qty", "Robe"),
	("utility_qty", "Utility"),
	("vanity_qty", "Vanity Unit"),
	("pantry_qty", "Pantry"),
)

# Kitchen is the primary unit; Utility gets its own project but shares kitchen_utility_manifest.
SUB_UNIT_PROJECT_QTY_COLUMNS = (
	("utility_qty", "Utility"),
	("robe_qty", "Robe"),
	("vanity_qty", "Vanity Unit"),
	("pantry_qty", "Pantry"),
)

SUB_UNIT_TYPES = tuple(project_type for _col, project_type in SUB_UNIT_PROJECT_QTY_COLUMNS)

IMPORT_ACTIONS = ("Created", "Updated", "Skipped", "Failed")


def kitchen_qty(qtys: dict[str, int]) -> int:
	return qtys.get("kitchen_qty", 0)


def has_kitchen_unit(qtys: dict[str, int]) -> bool:
	return kitchen_qty(qtys) > 0


def needs_kitchen_utility_manifest(qtys: dict[str, int]) -> bool:
	return qtys.get("kitchen_qty", 0) > 0 or qtys.get("utility_qty", 0) > 0
