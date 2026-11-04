# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""A site's unit projects at a glance: what each unit is (apartment, product, tender manifest,
spec, cabinets and the BOMs they're built from) and where it stands (dates, tasks, next stage,
early / on time / late against its delivery date, BR-PPP-07)."""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from fitzgerald_kitchens.manufacturing.project_manifest import (
	get_active_bom_no,
	is_manufacturing_item,
	resolve_project_effective_manifest,
)

DELIVERY_TASK_TYPE = "Delivery"
DONE = ("Completed", "Cancelled")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("site_project"):
		return get_columns(), []

	projects = frappe.get_all(
		"Project",
		filters={"fk_parent_project": filters.site_project},
		fields=[
			"name",
			"project_type",
			"status",
			"percent_complete",
			"expected_start_date",
			"expected_end_date",
			"fk_house_number",
			"fk_floor",
			"fk_tender_manifest",
		],
	)
	now = getdate(today())
	tender_manifests = {}
	rows = []
	for p in projects:
		tm = _tender_manifest(p.fk_tender_manifest, tender_manifests)
		tasks = frappe.get_all(
			"Task",
			filters={"project": p.name},
			fields=["subject", "type", "status", "exp_start_date", "exp_end_date", "act_end_date"],
			order_by="exp_start_date asc, idx asc",
		)
		open_tasks = [t for t in tasks if t.status not in DONE]
		next_task = open_tasks[0] if open_tasks else None
		delivery = next((t.exp_start_date for t in tasks if t.type == DELIVERY_TASK_TYPE), None) or p.expected_end_date
		rows.append(
			{
				"project": p.name,
				"apt_no": p.fk_house_number,
				"floor": p.fk_floor,
				"product": p.project_type,
				"tender_manifest": p.fk_tender_manifest,
				"manifest_name": tm["name"],
				"spec": tm["spec"],
				"cabinets": _cabinets(p.name),
				"start": p.expected_start_date,
				"delivery": getdate(delivery) if delivery else None,
				"tasks": f"{len(tasks) - len(open_tasks)} / {len(tasks)}",
				"percent_complete": flt(p.percent_complete),
				"next_stage": next_task.subject if next_task else _("All done"),
				"next_due": getdate(next_task.exp_end_date) if next_task and next_task.exp_end_date else None,
				"schedule": _schedule(tasks, next_task, now),
				"status": p.status,
			}
		)
	rows.sort(key=lambda r: (_apt_sort(r["apt_no"]), r["product"] != "Kitchen", r["product"] or ""))
	return get_columns(), rows


def _tender_manifest(name: str | None, cache: dict) -> dict:
	"""The tender manifest's name and its spec: the items on its spec-only rows (board, door ...)."""
	if not name:
		return {"name": None, "spec": None}
	if name not in cache:
		tender_name, rows_json = frappe.db.get_value("Tender Manifest", name, ["tender_name", "config_rows_json"])
		rows = json.loads(rows_json or "[]")
		spec = " / ".join(r["item_code"] for r in rows if r.get("exclude_from_price") and r.get("item_code"))
		cache[name] = {"name": tender_name, "spec": spec or None}
	return cache[name]


def _cabinets(project: str) -> str | None:
	"""The unit's cabinets and the BOM each is built from, e.g. "SB60 x5 (BOM-SB60-002)"."""
	manifest = resolve_project_effective_manifest(project)
	if not manifest:
		return None
	parts = []
	for line in frappe.get_all(
		"Manifest Item", filters={"parent": manifest}, fields=["item_code", "qty", "linked_bom"], order_by="idx"
	):
		if line.item_code and flt(line.qty) > 0 and is_manufacturing_item(line.item_code, line.linked_bom):
			parts.append(f"{line.item_code} x{flt(line.qty):g} ({get_active_bom_no(line.item_code, line.linked_bom)})")
	return ", ".join(parts) or None


def _schedule(tasks: list, next_task, now) -> str:
	"""Late when the next open stage is past its expected end; Early when everything finished before
	it was due; otherwise On Time."""
	if next_task:
		if next_task.exp_end_date and getdate(next_task.exp_end_date) < now:
			return "Late"
		return "On Time"
	finished_early = tasks and all(
		t.act_end_date and t.exp_end_date and getdate(t.act_end_date) < getdate(t.exp_end_date) for t in tasks
	)
	return "Early" if finished_early else "On Time"


def _apt_sort(apt_no: str | None):
	apt_no = apt_no or ""
	return (0, int(apt_no)) if apt_no.isdigit() else (1, apt_no)


def get_columns() -> list[dict]:
	return [
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 130},
		{"label": _("Apt No"), "fieldname": "apt_no", "fieldtype": "Data", "width": 70},
		{"label": _("Floor"), "fieldname": "floor", "fieldtype": "Data", "width": 60},
		{"label": _("Product"), "fieldname": "product", "fieldtype": "Link", "options": "Project Type", "width": 85},
		{"label": _("Schedule"), "fieldname": "schedule", "fieldtype": "Data", "width": 90},
		{"label": _("Next Stage"), "fieldname": "next_stage", "fieldtype": "Data", "width": 120},
		{"label": _("Next Due"), "fieldname": "next_due", "fieldtype": "Date", "width": 95},
		{"label": _("Tasks Done"), "fieldname": "tasks", "fieldtype": "Data", "width": 80},
		{"label": _("% Complete"), "fieldname": "percent_complete", "fieldtype": "Percent", "width": 90},
		{"label": _("Start"), "fieldname": "start", "fieldtype": "Date", "width": 95},
		{"label": _("Delivery"), "fieldname": "delivery", "fieldtype": "Date", "width": 95},
		{"label": _("Tender Manifest"), "fieldname": "tender_manifest", "fieldtype": "Link", "options": "Tender Manifest", "width": 120},
		{"label": _("Manifest Name"), "fieldname": "manifest_name", "fieldtype": "Data", "width": 150},
		{"label": _("Spec"), "fieldname": "spec", "fieldtype": "Data", "width": 300},
		{"label": _("Cabinets (BOM)"), "fieldname": "cabinets", "fieldtype": "Data", "width": 380},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 80},
	]
