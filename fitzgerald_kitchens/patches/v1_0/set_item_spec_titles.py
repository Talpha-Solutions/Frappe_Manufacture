# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.fitzgerald_kitchens.doctype.item_spec.item_spec import get_spec_title


def execute():
	"""Fill the new Item Spec title (spec list · reference) on existing specs."""
	for spec in frappe.get_all("Item Spec", fields=["name", "spec_list", "spec_reference"]):
		frappe.db.set_value(
			"Item Spec",
			spec.name,
			"spec_title",
			get_spec_title(spec.spec_list, spec.spec_reference),
			update_modified=False,
		)
