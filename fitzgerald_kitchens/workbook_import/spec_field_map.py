# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

# Spec Sheet row label (first column) -> Project Unit Configuration fieldname

SPEC_SECTION_LABELS = frozenset(
	{
		"Spec Type",
		"To Supply",
		"Tap & Sink",
		"Appliances",
		"Accessories",
		"Robes",
		"Utility",
		"Worktops & Splashbacks",
	}
)

SPEC_LABEL_TO_FIELD: dict[str, str] = {
	"Wall Unit Door": "wall_unit_door",
	"Wall Unit Carcass": "wall_unit_carcass",
	"Tall Unit Door": "tall_unit_door",
	"Tall Unit Carcass": "tall_unit_carcass",
	"Base Unit Door": "base_unit_door",
	"Base Unit Carcass": "base_unit_carcass",
	"Island Unit Door": "island_unit_door",
	"Island Unit Carcass": "island_unit_carcass",
	"Gables": "gables",
	"Tap": "tap",
	"Sink": "sink",
	"Flow Restrictor": "flow_restrictor",
	"Canope fan": "canope_fan",
	"Hob": "hob",
	"Oven": "oven",
	"Microwave": "microwave",
	"Fridge/freezer": "fridge_freezer",
	"Bins": "bins",
	"Cutlery": "cutlery",
	"Vents": "vents",
	"Kitchen Handles": "kitchen_handles",
	"Robes Handles": "robes_handles",
	"Robe Carcass": "robe_carcass",
	"Robe Door": "robe_door",
	"Robe Gables": "robe_gables",
	"Utility Unit": "utility_unit",
	"Utility Gable": "utility_gable",
	"Kitchen Worktop": "kitchen_worktop",
	"Kitchen Backsplash": "kitchen_backsplash",
	"Kitchen Upstand": "kitchen_upstand",
	"Utility Worktop": "utility_worktop",
	"Utility Worktop Upstand": "utility_worktop_upstand",
	"Dishwasher": "dishwasher",
	"Washing Machine": "washing_machine",
	"Dryer": "dryer",
}


def is_spec_section_label(label: str) -> bool:
	return (label or "").strip() in SPEC_SECTION_LABELS


def field_for_spec_label(label: str) -> str | None:
	return SPEC_LABEL_TO_FIELD.get((label or "").strip())
