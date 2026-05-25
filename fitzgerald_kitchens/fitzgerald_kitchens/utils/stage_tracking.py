# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import get_url, getdate, now_datetime, today

STAGE_STATUSES = ("Not Started", "Ongoing", "Completed", "Cancelled")

STAGE_SCHEDULE_STATUSES = ("Early", "On Time", "Late")
STAGE_SCHEDULE_INDICATORS = {
	"Early": "blue",
	"On Time": "green",
	"Late": "red",
}

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


def _stage_row_value(row, fieldname: str):
	if isinstance(row, dict):
		return row.get(fieldname)
	return getattr(row, fieldname, None)


def _stage_sort_key(row) -> tuple:
	return (_stage_row_value(row, "sequence") or 0, _stage_row_value(row, "idx") or 0)


def _is_later_stage(row, other) -> bool:
	row_key = _stage_sort_key(row)
	other_key = _stage_sort_key(other)
	return other_key > row_key


def has_later_completed_stage(row, all_stages) -> bool:
	"""True when a later stage is completed but this one is still open."""
	if not all_stages:
		return False

	status = normalize_stage_status(_stage_row_value(row, "status"))
	if status not in ("Not Started", "Ongoing"):
		return False

	row_name = _stage_row_value(row, "name")
	for other in all_stages:
		if row_name and _stage_row_value(other, "name") == row_name:
			continue
		if not _is_later_stage(row, other):
			continue
		if normalize_stage_status(_stage_row_value(other, "status")) == "Completed":
			return True
	return False


def get_stage_schedule_status(row, all_stages=None) -> str | None:
	"""Schedule vs plan, with sequence rule for skipped earlier stages."""
	if has_later_completed_stage(row, all_stages):
		return "Late"

	planned = _stage_row_value(row, "planned_date")
	if not planned:
		return None

	planned_date = getdate(planned)
	status = normalize_stage_status(_stage_row_value(row, "status"))

	if status == "Completed":
		actual = _stage_row_value(row, "actual_completion_date")
		compare_date = getdate(actual) if actual else getdate(today())
	else:
		compare_date = getdate(today())

	if compare_date < planned_date:
		return "Early"
	if compare_date > planned_date:
		return "Late"
	return "On Time"


def get_stage_schedule_indicator(row, all_stages=None) -> str:
	"""Frappe indicator color for a stage row (blue / green / red)."""
	status = get_stage_schedule_status(row, all_stages)
	return STAGE_SCHEDULE_INDICATORS.get(status, "gray")


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


# Share of the gap to the next milestone while the next stage is in progress.
ONGOING_STAGE_GAP_FRACTION = 0.5


def _gap_fill_fraction(status: str | None) -> float:
	status = normalize_stage_status(status)
	if status == "Ongoing":
		return ONGOING_STAGE_GAP_FRACTION
	return 0.0


def _next_non_cancelled_index(sorted_stages, after_index: int) -> int | None:
	for index in range(after_index + 1, len(sorted_stages)):
		if normalize_stage_status(_stage_row_value(sorted_stages[index], "status")) != "Cancelled":
			return index
	return None


def get_stage_progress_percentage(stages) -> float:
	"""Milestone % of latest completed stage plus a share of the gap to the next stage.

	The gap is ``next_stage.progress_percentage - latest_completed.progress_percentage``.
	That gap is filled based on the next (current) stage status:
	- Not Started: 0% of the gap (stay on the last milestone)
	- Ongoing: 50% of the gap (midpoint between milestones)
	"""
	if not stages:
		return 0.0

	sorted_stages = sorted(stages, key=_stage_sort_key)
	last_completed_index = None

	for index, row in enumerate(sorted_stages):
		if normalize_stage_status(_stage_row_value(row, "status")) == "Completed":
			last_completed_index = index

	if last_completed_index is None:
		floor = 0.0
		next_index = _next_non_cancelled_index(sorted_stages, -1)
		if next_index is None:
			return 0.0
		next_row = sorted_stages[next_index]
		ceiling = float(_stage_row_value(next_row, "progress_percentage") or 0)
		gap = max(0.0, ceiling - floor)
		fill = _gap_fill_fraction(_stage_row_value(next_row, "status"))
		return min(100.0, floor + gap * fill)

	last_row = sorted_stages[last_completed_index]
	base = float(_stage_row_value(last_row, "progress_percentage") or 0)

	next_index = _next_non_cancelled_index(sorted_stages, last_completed_index)
	if next_index is None:
		return min(100.0, base)

	next_row = sorted_stages[next_index]
	next_pct = float(_stage_row_value(next_row, "progress_percentage") or 0)
	gap = max(0.0, next_pct - base)
	fill = _gap_fill_fraction(_stage_row_value(next_row, "status"))

	return min(100.0, base + gap * fill)


def get_current_stage_row(stages):
	"""Stage after the latest completed row; first stage if none completed yet."""
	if not stages:
		return None

	sorted_stages = sorted(stages, key=_stage_sort_key)
	last_completed_index = None

	for index, row in enumerate(sorted_stages):
		if normalize_stage_status(_stage_row_value(row, "status")) == "Completed":
			last_completed_index = index

	if last_completed_index is None:
		return sorted_stages[0]

	next_index = last_completed_index + 1
	if next_index < len(sorted_stages):
		return sorted_stages[next_index]

	return sorted_stages[last_completed_index]


def sync_unit_progress_from_stages(doc) -> None:
	"""Sync Development Unit header fields from its stage rows."""
	if not doc.stages:
		return

	current = get_current_stage_row(doc.stages)
	if not current:
		return

	doc.current_stage = _stage_row_value(current, "stage")
	if hasattr(doc, "current_stage_progress"):
		doc.current_stage_progress = get_stage_progress_percentage(doc.stages)
