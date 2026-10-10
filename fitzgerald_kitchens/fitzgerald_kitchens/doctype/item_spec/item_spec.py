# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import bold


class ItemSpec(Document):
	def validate(self):
		self.validate_item()
		self.validate_spec_list()
		self.check_duplicates()
		self.spec_title = get_spec_title(self.spec_list, self.spec_reference)

	def validate_item(self):
		if not frappe.db.exists("Item", self.item_code):
			frappe.throw(_("Item {0} not found.").format(self.item_code))

		if frappe.get_cached_value("Item", self.item_code, "has_variants"):
			frappe.throw(
				_("Item Spec cannot be created for the template item {0}.").format(bold(self.item_code))
			)

	def validate_spec_list(self):
		if not frappe.db.get_value("Spec List", self.spec_list, "enabled"):
			frappe.throw(_("Spec List {0} is disabled.").format(bold(self.spec_list)))

	def check_duplicates(self):
		existing = frappe.db.exists(
			"Item Spec",
			{"item_code": self.item_code, "spec_list": self.spec_list, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(
				_("Item {0} already has a spec in Spec List {1}: {2}").format(
					bold(self.item_code), bold(self.spec_list), frappe.get_desk_link("Item Spec", existing)
				),
				title=_("Duplicate Item Spec"),
			)


def get_spec_title(spec_list: str | None, spec_reference: str | None) -> str:
	"""e.g. "Standard Spec · N11 360", the title shown wherever an Item Spec is linked."""
	return " · ".join(filter(None, [spec_list, spec_reference]))


@frappe.whitelist()
def get_item_specs(item_code: str):
	"""Fetch item specs for the Item Specs table on the Item form (mirrors get_item_prices)."""
	if not frappe.has_permission("Item Spec", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	ItemSpec = frappe.qb.DocType("Item Spec")
	SpecList = frappe.qb.DocType("Spec List")

	specs = (
		frappe.qb.from_(ItemSpec)
		.left_join(SpecList)
		.on(SpecList.name == ItemSpec.spec_list)
		.select(
			ItemSpec.name,
			ItemSpec.spec_list,
			ItemSpec.spec_reference,
			ItemSpec.specification,
			SpecList.enabled,
		)
		.where(ItemSpec.item_code == item_code)
		.orderby(ItemSpec.spec_list)
		.limit(11)
		.run(as_dict=True)
	)

	return {
		"specs": specs[:10],
		"has_more": len(specs) == 11,
	}


@frappe.whitelist()
def get_spec_options(item_codes) -> dict:
	"""Item Specs per item code, for the SPEC dropdown in the Tender Manifest builder."""
	if not frappe.has_permission("Item Spec", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	item_codes = [code for code in frappe.parse_json(item_codes) or [] if code]
	if not item_codes:
		return {}

	ItemSpec = frappe.qb.DocType("Item Spec")
	SpecList = frappe.qb.DocType("Spec List")

	specs = (
		frappe.qb.from_(ItemSpec)
		.left_join(SpecList)
		.on(SpecList.name == ItemSpec.spec_list)
		.select(
			ItemSpec.name,
			ItemSpec.item_code,
			ItemSpec.spec_list,
			ItemSpec.spec_reference,
			ItemSpec.specification,
			SpecList.enabled,
		)
		.where(ItemSpec.item_code.isin(item_codes))
		.orderby(SpecList.enabled, order=frappe.qb.desc)
		.orderby(ItemSpec.spec_list)
		.run(as_dict=True)
	)

	options = {}
	for spec in specs:
		options.setdefault(spec.item_code, []).append(spec)
	return options
