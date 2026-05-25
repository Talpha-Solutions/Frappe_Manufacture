# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


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


@frappe.whitelist()
def create_kitchen_work_order(project: str, bom_no: str, item: str | None = None, qty: float | None = None):
	"""Create a Work Order from the project's Kitchen BOM and link it on the Project."""
	return _create_project_work_order(project, bom_no, item, qty, "kitchen_work_order")


@frappe.whitelist()
def create_wardrobe_work_order(project: str, bom_no: str, item: str | None = None, qty: float | None = None):
	"""Create a Work Order from the project's Wardrobe BOM and link it on the Project."""
	return _create_project_work_order(project, bom_no, item, qty, "wardrobe_work_order")


def _create_project_work_order(
	project: str,
	bom_no: str,
	item: str | None,
	qty: float | None,
	project_work_order_field: str,
) -> str:
	if not project or not bom_no:
		frappe.throw(_("Project and BOM are required to create a Work Order"))

	if not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} does not exist").format(project))

	bom = frappe.db.get_value(
		"BOM",
		bom_no,
		["name", "item", "quantity", "docstatus", "company"],
		as_dict=True,
	)
	if not bom:
		frappe.throw(_("BOM {0} does not exist").format(bom_no))

	if bom.docstatus != 1:
		frappe.throw(_("BOM {0} must be submitted before creating a Work Order").format(bom_no))

	production_item = item or bom.item
	if not production_item:
		frappe.throw(_("Production Item is required to create a Work Order"))

	company = frappe.db.get_value("Project", project, "company")
	if not company:
		frappe.throw(_("Set Company on the Project before creating a Work Order"))

	work_order_qty = flt(qty) or flt(bom.quantity) or 1

	from erpnext.manufacturing.doctype.work_order.work_order import make_work_order

	wo = make_work_order(
		bom_no=bom_no,
		item=production_item,
		qty=work_order_qty,
		project=project,
	)
	wo.company = company
	if not wo.qty:
		wo.qty = work_order_qty
	wo.get_items_and_operations_from_bom()
	wo.insert()

	frappe.db.set_value("Project", project, project_work_order_field, wo.name, update_modified=False)

	return wo.name
