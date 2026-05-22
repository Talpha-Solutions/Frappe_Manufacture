# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class KitchenBOMMapping(Document):
	def validate(self):
		self.validate_unique_combination()

	def validate_unique_combination(self):
		if not (self.kitchen_type and self.kitchen_specification):
			return

		existing = frappe.db.exists(
			"Kitchen BOM Mapping",
			{
				"kitchen_type": self.kitchen_type,
				"kitchen_specification": self.kitchen_specification,
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				_(
					"A Kitchen BOM Mapping already exists for Kitchen Type {0} and Kitchen Specification {1}"
				).format(self.kitchen_type, self.kitchen_specification)
			)


def get_kitchen_bom_for_mapping(kitchen_type: str, kitchen_specification: str) -> dict | None:
	"""Return kitchen BOM (and item) for a type + specification combination."""
	if not kitchen_type or not kitchen_specification:
		return None

	mapping_name = frappe.db.get_value(
		"Kitchen BOM Mapping",
		{
			"kitchen_type": kitchen_type,
			"kitchen_specification": kitchen_specification,
		},
		["name", "kitchen_bom", "kitchen_item"],
		as_dict=True,
	)
	if not mapping_name:
		return None

	result = {"kitchen_bom": mapping_name.kitchen_bom}

	if mapping_name.kitchen_item:
		result["kitchen_item"] = mapping_name.kitchen_item
	elif mapping_name.kitchen_bom:
		result["kitchen_item"] = frappe.db.get_value("BOM", mapping_name.kitchen_bom, "item")

	return result
