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


def _is_despatch_task(task_name: str) -> bool:
	task_type = normalize_label_scan_task_type(frappe.db.get_value("Task", task_name, "type"))
	return task_type == DESPATCH_TASK_TYPE


def _get_task_scanned_item_quantities(task_name: str) -> dict[str, float]:
	qty_map: dict[str, float] = {}
	rows = frappe.get_all(
		"Task Label Scan Log",
		filters={"task": task_name, "status": "Scanned", "item_code": ["is", "set"]},
		fields=["item_code"],
	)
	for row in rows:
		item_code = row.item_code
		qty_map[item_code] = qty_map.get(item_code, 0) + 1
	return qty_map


def _get_project_company_warehouse(project: str) -> tuple[str | None, str | None]:
	company = frappe.db.get_value("Project", project, "company")
	warehouse = frappe.db.get_value("Project", project, "default_warehouse")
	if not warehouse and company:
		warehouse = frappe.db.get_value("Company", company, "default_warehouse")
	if not warehouse:
		warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	return company, warehouse


def _find_existing_material_request(project: str) -> str | None:
	for docstatus in (1, 0):
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
	return None


def _make_stock_entry_from_mr(mr_name: str):
	try:
		from erpnext.stock.doctype.material_request.material_request import make_stock_entry
	except ImportError:
		frappe.throw(_("ERPNext is required for Despatch material requests."))

	return frappe.get_doc(make_stock_entry(mr_name))


def _issue_items_from_mr(mr_name: str, item_qty_map: dict[str, float]) -> str | None:
	if not item_qty_map:
		return None

	stock_entry = _make_stock_entry_from_mr(mr_name)
	kept_rows = []
	for row in stock_entry.items:
		if row.item_code not in item_qty_map:
			continue
		row.qty = flt(item_qty_map[row.item_code])
		if row.qty > 0:
			kept_rows.append(row)

	if not kept_rows:
		return None

	stock_entry.set("items", kept_rows)
	stock_entry.save(ignore_permissions=True)
	stock_entry.submit()
	return stock_entry.name


def _remove_issued_items_from_draft_mr(mr_name: str, issued_item_codes: set[str]) -> None:
	mr = frappe.get_doc("Material Request", mr_name)
	if mr.docstatus != 0:
		return

	mr.items = [row for row in mr.items if row.item_code not in issued_item_codes]
	if not mr.items:
		mr.delete(ignore_permissions=True)
		return

	mr.save(ignore_permissions=True)
	mr.submit()


def _create_material_request(project: str, item_qty_map: dict[str, float], company: str) -> frappe.model.document.Document:
	mr = frappe.new_doc("Material Request")
	mr.material_request_type = "Material Transfer"
	mr.company = company
	mr.project = project
	mr.transaction_date = today()
	mr.schedule_date = today()

	_, warehouse = _get_project_company_warehouse(project)
	for item_code, qty in sorted(item_qty_map.items()):
		row = {
			"item_code": item_code,
			"qty": flt(qty),
			"schedule_date": today(),
		}
		if warehouse:
			row["warehouse"] = warehouse
		mr.append("items", row)

	mr.insert(ignore_permissions=True)
	mr.submit()
	return mr


def _split_scanned_items_against_mr(
	mr_doc: frappe.model.document.Document, scanned_qty: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
	"""Return (qty to issue from existing MR, qty for a new MR)."""
	mr_qty = {row.item_code: flt(row.qty) for row in mr_doc.items}
	issue_from_existing: dict[str, float] = {}
	remainder_for_new_mr: dict[str, float] = {}

	for item_code, scanned in scanned_qty.items():
		available = mr_qty.get(item_code, 0)
		if available > 0:
			issue_qty = min(scanned, available)
			issue_from_existing[item_code] = issue_qty
			leftover = scanned - issue_qty
			if leftover > 0:
				remainder_for_new_mr[item_code] = leftover
		else:
			remainder_for_new_mr[item_code] = scanned

	return issue_from_existing, remainder_for_new_mr


@frappe.whitelist()
def sync_despatch_material_request(task_name: str) -> dict | None:
	"""Lightweight hook during scanning — MR is finalized on task completion."""
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
	"""
	After all Despatch labels are scanned and the task completes:
	1. Issue scanned items that exist on the project's Material Request, then update/submit it.
	2. Create a new Material Request for any remaining scanned items and issue them too.
	"""
	if not _is_despatch_task(task_name):
		return None

	task = frappe.db.get_value("Task", task_name, ["project", "name"], as_dict=True)
	if not task or not task.project:
		return None

	scanned_qty = _get_task_scanned_item_quantities(task_name)
	if not scanned_qty:
		return None

	company, _warehouse = _get_project_company_warehouse(task.project)
	if not company:
		frappe.throw(_("Set a Company on project {0} before completing Despatch.").format(task.project))

	existing_mr_name = _find_existing_material_request(task.project)
	issue_from_existing: dict[str, float] = {}
	remainder_for_new_mr = dict(scanned_qty)
	stock_entries: list[str] = []
	result_mr_name = existing_mr_name

	if existing_mr_name:
		mr_doc = frappe.get_doc("Material Request", existing_mr_name)
		issue_from_existing, remainder_for_new_mr = _split_scanned_items_against_mr(mr_doc, scanned_qty)

		if issue_from_existing:
			stock_entry = _issue_items_from_mr(existing_mr_name, issue_from_existing)
			if stock_entry:
				stock_entries.append(stock_entry)
			_remove_issued_items_from_draft_mr(existing_mr_name, set(issue_from_existing.keys()))
			result_mr_name = existing_mr_name

	if remainder_for_new_mr:
		new_mr = _create_material_request(task.project, remainder_for_new_mr, company)
		result_mr_name = new_mr.name
		stock_entry = _issue_items_from_mr(new_mr.name, remainder_for_new_mr)
		if stock_entry:
			stock_entries.append(stock_entry)

	return {
		"name": result_mr_name,
		"updated": bool(issue_from_existing or remainder_for_new_mr),
		"stock_entries": stock_entries,
		"existing_mr": existing_mr_name,
		"issued_from_existing": issue_from_existing,
		"issued_from_new_mr": remainder_for_new_mr,
	}
