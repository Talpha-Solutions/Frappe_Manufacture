# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, today

from fitzgerald_kitchens.fitzgerald_kitchens.page.task_scan.label_scan import (
	normalize_label_scan_task_type,
)

DESPATCH_TASK_TYPE = "Despatch"
DESPATCH_NEW_MR_WAREHOUSE = "Finished Goods - FKD"
DESPATCH_NEW_MR_TYPE = "Material Issue"


def _is_despatch_task(task_name: str) -> bool:
	task_type = normalize_label_scan_task_type(frappe.db.get_value("Task", task_name, "type"))
	return task_type == DESPATCH_TASK_TYPE


def _get_task_scanned_item_quantities(task_name: str) -> dict[str, float]:
	qty_map: dict[str, float] = {}
	rows = frappe.get_all(
		"Task Label Scan Log",
		filters={"task": task_name, "status": "Scanned"},
		fields=["item_code", "item_instance_code"],
	)
	for row in rows:
		item_code = row.item_code
		if not item_code and row.item_instance_code:
			item_code = _item_code_from_instance(row.item_instance_code, task_name)
		if not item_code:
			continue
		qty_map[item_code] = qty_map.get(item_code, 0) + 1
	return qty_map


def _item_code_from_instance(item_instance_code: str, task_name: str) -> str | None:
	project = frappe.db.get_value("Task", task_name, "project")
	if not project:
		return None
	from fitzgerald_kitchens.setup.project_qr_labels import expand_manifest_item_instances

	for row in expand_manifest_item_instances(project):
		if row.get("item_instance_code") == item_instance_code:
			return row.get("item_code")
	return None


def _get_despatch_new_mr_warehouse(company: str | None) -> str:
	if frappe.db.exists("Warehouse", DESPATCH_NEW_MR_WAREHOUSE):
		return DESPATCH_NEW_MR_WAREHOUSE

	filters = {"warehouse_name": "Finished Goods"}
	if company:
		filters["company"] = company
	name = frappe.db.get_value("Warehouse", filters, "name")
	if name:
		return name

	frappe.throw(
		_("Warehouse {0} was not found. Create it before completing Despatch.").format(
			DESPATCH_NEW_MR_WAREHOUSE
		)
	)


def _get_project_company(project: str) -> str | None:
	return frappe.db.get_value("Project", project, "company")


def _find_existing_material_request(project: str) -> str | None:
	for docstatus in (0, 1):
		name = frappe.db.get_value(
			"Material Request",
			{
				"project": project,
				"docstatus": docstatus,
				"status": ["not in", ["Stopped", "Cancelled", "Closed"]],
			},
			order_by="modified desc",
		)
		if name:
			return name

	item_parents = frappe.db.sql(
		"""
		select parent
		from `tabMaterial Request Item`
		where project = %s
		order by modified desc
		limit 1
		""",
		project,
	)
	if item_parents:
		mr_name = item_parents[0][0]
		if frappe.db.get_value("Material Request", mr_name, "docstatus") in (0, 1):
			return mr_name
	return None


def _mr_item_qty_map(mr_doc) -> dict[str, float]:
	qty_map: dict[str, float] = {}
	for row in mr_doc.items:
		qty_map[row.item_code] = qty_map.get(row.item_code, 0) + flt(row.qty)
	return qty_map


def _submit_draft_mr(mr_doc) -> str:
	mr_doc.flags.ignore_permissions = True
	if mr_doc.docstatus == 0:
		mr_doc.submit()
	return mr_doc.name


def _create_material_request(
	project: str,
	item_qty_map: dict[str, float],
	company: str,
	*,
	warehouse: str,
) -> frappe.model.document.Document:
	mr = frappe.new_doc("Material Request")
	mr.material_request_type = DESPATCH_NEW_MR_TYPE
	mr.company = company
	mr.project = project
	mr.transaction_date = today()
	mr.schedule_date = today()
	mr.set_warehouse = warehouse

	for item_code, qty in sorted(item_qty_map.items()):
		mr.append(
			"items",
			{
				"item_code": item_code,
				"qty": flt(qty),
				"schedule_date": today(),
				"project": project,
				"warehouse": warehouse,
			},
		)

	mr.flags.ignore_permissions = True
	mr.insert(ignore_permissions=True)
	mr.submit()
	return mr


def _scanned_items_not_on_mr(mr_doc, scanned_qty: dict[str, float]) -> dict[str, float]:
	mr_qty = _mr_item_qty_map(mr_doc)
	return {
		item_code: qty
		for item_code, qty in scanned_qty.items()
		if item_code not in mr_qty
	}


@frappe.whitelist()
def sync_despatch_material_request(task_name: str) -> dict | None:
	if not _is_despatch_task(task_name):
		return None

	project = frappe.db.get_value("Task", task_name, "project")
	if not project:
		return None

	return {
		"name": _find_existing_material_request(project),
		"updated": False,
	}


@frappe.whitelist()
def submit_despatch_material_request(task_name: str) -> dict | None:
	if not _is_despatch_task(task_name):
		return {"skipped": True, "reason": "not_despatch_task"}

	task = frappe.db.get_value("Task", task_name, ["project", "name"], as_dict=True)
	if not task or not task.project:
		return {"skipped": True, "reason": "no_project"}

	scanned_qty = _get_task_scanned_item_quantities(task_name)
	if not scanned_qty:
		return {"skipped": True, "reason": "no_scanned_items"}

	company = _get_project_company(task.project)
	if not company:
		frappe.throw(_("Set a Company on project {0} before completing Despatch.").format(task.project))

	new_mr_warehouse = _get_despatch_new_mr_warehouse(company)
	existing_mr_name = _find_existing_material_request(task.project)
	mr_doc = frappe.get_doc("Material Request", existing_mr_name) if existing_mr_name else None

	submitted_existing_mr = None
	new_mr_name = None
	new_mr_items: dict[str, float] = dict(scanned_qty)
	errors: list[str] = []

	if mr_doc:
		new_mr_items = _scanned_items_not_on_mr(mr_doc, scanned_qty)
		if mr_doc.docstatus == 0:
			try:
				submitted_existing_mr = _submit_draft_mr(mr_doc)
			except Exception as exc:
				errors.append(str(exc))
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Despatch draft MR submit failed for {task_name}",
				)

	if new_mr_items:
		try:
			new_mr = _create_material_request(
				task.project,
				new_mr_items,
				company,
				warehouse=new_mr_warehouse,
			)
			new_mr_name = new_mr.name
		except Exception as exc:
			errors.append(str(exc))
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Despatch new MR create failed for {task_name}",
			)

	frappe.db.commit()

	return {
		"name": new_mr_name or submitted_existing_mr or existing_mr_name,
		"updated": bool(submitted_existing_mr or new_mr_name),
		"existing_mr": existing_mr_name,
		"submitted_existing_mr": submitted_existing_mr,
		"new_mr": new_mr_name,
		"new_mr_warehouse": new_mr_warehouse,
		"new_mr_items": new_mr_items,
		"errors": errors,
	}
