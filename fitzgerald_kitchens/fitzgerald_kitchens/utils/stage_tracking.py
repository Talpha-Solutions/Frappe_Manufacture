# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

STAGE_STATUSES = ("Not Started", "Ongoing", "Completed", "Cancelled")

LEGACY_STAGE_STATUS_MAP = {
	"Pending": "Not Started",
	"In Progress": "Ongoing",
	"Completed": "Completed",
	"Skipped": "Cancelled",
	"Failed": "Cancelled",
	"On Hold": "Ongoing",
}


def normalize_stage_status(value: str | None) -> str:
	if value in STAGE_STATUSES:
		return value
	return LEGACY_STAGE_STATUS_MAP.get(value, "Not Started")


def resolve_development_unit_from_qr(qr_text: str) -> str:
	"""Resolve a Development Unit name from a scanned QR value or URL."""
	qr_text = (qr_text or "").strip()
	if not qr_text:
		frappe.throw(_("Empty QR code"))

	if frappe.db.exists("Development Unit", qr_text):
		return qr_text

	candidate = qr_text
	if "/" in qr_text:
		candidate = qr_text.rstrip("/").split("/")[-1]
		candidate = candidate.split("?")[0]

	if frappe.db.exists("Development Unit", candidate):
		return candidate

	frappe.throw(_("No Development Unit found for this QR code"))


def get_qr_code_value(doc_name: str) -> str:
	return get_url(f"/app/development-unit/{doc_name}")


def get_stage_rows_for_unit(development_unit: str) -> list[dict]:
	"""Return stage rows from a Development Unit for QR scan UI."""
	rows = frappe.get_all(
		"Development Unit Stage",
		filters={"parent": development_unit},
		fields=[
			"name",
			"stage",
			"sequence",
			"status",
			"progress_percentage",
			"process_tracked",
			"planned_date",
			"actual_start_date",
			"actual_completion_date",
		],
		order_by="sequence asc, idx asc",
	)
	for row in rows:
		row["status"] = normalize_stage_status(row.get("status"))
	return rows


def apply_stage_row_update(stage_row, new_status: str, process_tracked: bool = False) -> None:
	"""Update a Development Unit Stage child row in memory."""
	new_status = normalize_stage_status(new_status)
	stage_row.status = new_status

	if process_tracked:
		stage_row.process_tracked = 1

	now = now_datetime()
	user = frappe.session.user

	if new_status == "Ongoing":
		if not stage_row.actual_start_date:
			stage_row.actual_start_date = now
		return

	if new_status == "Completed":
		if not stage_row.actual_start_date:
			stage_row.actual_start_date = now
		stage_row.actual_completion_date = now
		stage_row.completed_by = user
		return

	if new_status == "Cancelled":
		stage_row.actual_completion_date = None
		stage_row.completed_by = None
		return

	if new_status == "Not Started":
		stage_row.actual_start_date = None
		stage_row.actual_completion_date = None
		stage_row.completed_by = None


def sync_unit_progress_from_stages(doc) -> None:
	"""Sync Development Unit header fields from its stage rows."""
	if not doc.stages:
		return

	stages = sorted(doc.stages, key=lambda row: (row.sequence or 0, row.idx or 0))
	ongoing = [row for row in stages if row.status == "Ongoing"]
	completed = [row for row in stages if row.status == "Completed"]

	if ongoing:
		current = ongoing[0]
	elif completed:
		current = completed[-1]
	else:
		not_started = [row for row in stages if row.status == "Not Started"]
		current = not_started[0] if not_started else stages[0]

	doc.current_stage = current.stage
	doc.progress_percentage = current.progress_percentage or 0

	if all(row.status == "Completed" for row in stages):
		doc.unit_status = "Completed"
		doc.schedule_status = "Completed"
	elif all(row.status == "Cancelled" for row in stages):
		doc.unit_status = "Cancelled"
	elif any(row.status in ("Ongoing", "Completed") for row in stages):
		doc.unit_status = "In Progress"
	else:
		doc.unit_status = "Planned"
