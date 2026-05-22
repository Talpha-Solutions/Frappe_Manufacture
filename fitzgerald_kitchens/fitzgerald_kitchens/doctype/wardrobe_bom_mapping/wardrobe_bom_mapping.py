# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WardrobeBOMMapping(Document):
	def validate(self):
		self.validate_unique_combination()

	def validate_unique_combination(self):
		if not (self.wardrobe_type and self.wardrobe_specification):
			return

		existing = frappe.db.exists(
			"Wardrobe BOM Mapping",
			{
				"wardrobe_type": self.wardrobe_type,
				"wardrobe_specification": self.wardrobe_specification,
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				_(
					"A Wardrobe BOM Mapping already exists for Wardrobe Type {0} and Wardrobe Specification {1}"
				).format(self.wardrobe_type, self.wardrobe_specification)
			)


def get_wardrobe_bom_for_mapping(wardrobe_type: str, wardrobe_specification: str) -> dict | None:
	"""Return wardrobe BOM (and item) for a type + specification combination."""
	if not wardrobe_type or not wardrobe_specification:
		return None

	mapping = frappe.db.get_value(
		"Wardrobe BOM Mapping",
		{
			"wardrobe_type": wardrobe_type,
			"wardrobe_specification": wardrobe_specification,
		},
		["name", "wardrobe_bom", "wardrobe_item"],
		as_dict=True,
	)
	if not mapping:
		return None

	result = {"wardrobe_bom": mapping.wardrobe_bom}

	if mapping.wardrobe_item:
		result["wardrobe_item"] = mapping.wardrobe_item
	elif mapping.wardrobe_bom:
		result["wardrobe_item"] = frappe.db.get_value("BOM", mapping.wardrobe_bom, "item")

	return result
