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

QTY_COLUMNS = (
	("kitchen_qty", KITCHEN_PROJECT_TYPE),
	("robe_qty", "Robe"),
	("utility_qty", "Utility"),
	("vanity_qty", "Vanity Unit"),
	("pantry_qty", "Pantry"),
)

SUB_UNIT_TYPES = ("Robe", "Utility", "Vanity Unit", "Pantry")

IMPORT_ACTIONS = ("Created", "Updated", "Skipped", "Failed")
