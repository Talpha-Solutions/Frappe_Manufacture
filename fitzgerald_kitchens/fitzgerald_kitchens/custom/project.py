# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_kitchen_bom_from_mapping(kitchen_type: str, kitchen_specification: str):
	"""Return Kitchen BOM and Item for the selected type + specification."""
	from fitzgerald_kitchens.fitzgerald_kitchens.doctype.kitchen_bom_mapping.kitchen_bom_mapping import (
		get_kitchen_bom_for_mapping,
	)

	return get_kitchen_bom_for_mapping(kitchen_type, kitchen_specification)


@frappe.whitelist()
def get_wardrobe_bom_from_mapping(wardrobe_type: str, wardrobe_specification: str):
	"""Return Wardrobe BOM and Item for the selected type + specification."""
	from fitzgerald_kitchens.fitzgerald_kitchens.doctype.wardrobe_bom_mapping.wardrobe_bom_mapping import (
		get_wardrobe_bom_for_mapping,
	)

	return get_wardrobe_bom_for_mapping(wardrobe_type, wardrobe_specification)
