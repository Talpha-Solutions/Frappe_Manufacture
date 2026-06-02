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
def create_work_order(
	project: str,
	bom_no: str,
	item: str | None = None,
	qty: float | None = None,
	sales_order: str | None = None,
):
	"""Create a Work Order from the project's Effective BOM (Unit tab)."""
	return _create_project_work_order(project, bom_no, item, qty, "fk_work_order", sales_order)


@frappe.whitelist()
def create_kitchen_work_order(
	project: str,
	bom_no: str,
	item: str | None = None,
	qty: float | None = None,
	sales_order: str | None = None,
):
	"""Deprecated: use create_work_order with fk_effective_bom."""
	return create_work_order(project, bom_no, item, qty, sales_order)


@frappe.whitelist()
def create_wardrobe_work_order(
	project: str,
	bom_no: str,
	item: str | None = None,
	qty: float | None = None,
	sales_order: str | None = None,
):
	"""Deprecated: use create_work_order with fk_effective_bom."""
	return create_work_order(project, bom_no, item, qty, sales_order)


def _create_project_work_order(
	project: str,
	bom_no: str,
	item: str | None,
	qty: float | None,
	project_work_order_field: str,
	sales_order: str | None = None,
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

	project_details = frappe.db.get_value(
		"Project",
		project,
		["company", "sales_order"],
		as_dict=True,
	)
	company = project_details.company
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

	sales_order_to_link = sales_order or project_details.sales_order

	wo.get_items_and_operations_from_bom()
	_set_work_order_sales_order_before_insert(wo, sales_order_to_link, production_item)
	wo.insert()
	_link_sales_order_after_insert(wo.name, sales_order_to_link)

	frappe.db.set_value("Project", project, project_work_order_field, wo.name, update_modified=False)

	return wo.name


def _set_work_order_sales_order_before_insert(
	wo,
	sales_order: str | None,
	production_item: str,
) -> None:
	"""Set Sales Order on Work Order before insert when ERPNext validation allows it."""
	if not sales_order:
		return

	so_link = _get_sales_order_item_link(sales_order, production_item)
	if not so_link:
		return

	wo.sales_order = sales_order
	wo.sales_order_item = so_link["sales_order_item"]
	if so_link.get("product_bundle_item"):
		wo.product_bundle_item = so_link["product_bundle_item"]


def _link_sales_order_after_insert(work_order: str, sales_order: str | None) -> None:
	"""Link Sales Order when manufacturing item is not a Sales Order line (e.g. kit BOM item).

	ERPNext blocks insert when sales_order is set but production_item is not on that order.
	Manufacturing often uses a kit item (BOM item) while the Sales Order lists sellable SKUs.
	"""
	if not sales_order or frappe.db.get_value("Work Order", work_order, "sales_order"):
		return

	frappe.db.set_value(
		"Work Order",
		work_order,
		"sales_order",
		sales_order,
		update_modified=False,
	)


def _get_sales_order_item_link(sales_order: str, production_item: str) -> dict | None:
	"""Resolve Sales Order Item when the manufacturing item appears on the Sales Order."""
	so_item = frappe.db.get_value(
		"Sales Order Item",
		{"parent": sales_order, "item_code": production_item},
		"name",
	)
	if so_item:
		return {"sales_order_item": so_item}

	bundle_match = frappe.db.sql(
		"""
		select soi.name as sales_order_item, soi.item_code as product_bundle_item
		from `tabSales Order Item` soi
		inner join `tabProduct Bundle Item` pbi on pbi.parent = soi.item_code
		where soi.parent = %s and pbi.item_code = %s
		limit 1
		""",
		(sales_order, production_item),
		as_dict=True,
	)
	if bundle_match:
		return bundle_match[0]

	packed_match = frappe.db.sql(
		"""
		select soi.name as sales_order_item, pi.parent_item as product_bundle_item
		from `tabSales Order Item` soi
		inner join `tabPacked Item` pi on pi.parent = soi.parent
		where soi.parent = %s and pi.item_code = %s
		limit 1
		""",
		(sales_order, production_item),
		as_dict=True,
	)
	if packed_match:
		return packed_match[0]

	return None
