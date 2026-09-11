# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Atomic, offline-syncable mutators for Development Unit.

Each function here does one focused change and returns a small dict the
client can use to refresh its local cache (`modified`, current rollups) —
none of them require the caller to build or resend the whole Development
Unit document, unlike the existing `DevelopmentUnitQRScan.apply_stage_updates`
whole-doc-save pattern.

Stage transitions (`start_stage`/`complete_stage`) are stateful — two
devices can race to change the same stage — so they take an optional
`based_on_modified` and go through `assert_not_stale`. Everything else here
(labour, material, issues, evidence) is purely additive: a new child row
appended to the Development Unit's child tables, which can never conflict
with another device's addition, so no staleness check is needed or taken.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.validation import assert_not_stale
from fitzgerald_kitchens.fitzgerald_kitchens.utils import stage_tracking


def _get_unit(development_unit: str):
	du = frappe.get_doc("Development Unit", development_unit)
	du.check_permission("write")
	return du


def _get_stage_row(du, stage_row_name: str):
	for row in du.stages:
		if row.name == stage_row_name:
			return row
	frappe.throw(_("Stage row {0} not found on {1}").format(stage_row_name, du.name))


def _mutate_stage(development_unit, stage_row_name, new_status, based_on_modified=None, notes=None):
	du = _get_unit(development_unit)
	assert_not_stale(du, based_on_modified)

	row = _get_stage_row(du, stage_row_name)
	stage_tracking.apply_stage_row_update(row, new_status)
	if notes is not None:
		row.notes = notes

	stage_tracking.sync_unit_progress_from_stages(du)
	du.save(ignore_permissions=True)
	du.reload()

	return {
		"development_unit": du.name,
		"stage_row_name": stage_row_name,
		"status": row.status,
		"current_stage": du.current_stage,
		"current_stage_progress": du.current_stage_progress,
		"modified": str(du.modified),
	}


@frappe.whitelist()
def start_stage(development_unit: str, stage_row_name: str, based_on_modified: str | None = None) -> dict:
	return _mutate_stage(development_unit, stage_row_name, "Ongoing", based_on_modified)


@frappe.whitelist()
def complete_stage(
	development_unit: str,
	stage_row_name: str,
	based_on_modified: str | None = None,
	notes: str | None = None,
) -> dict:
	return _mutate_stage(development_unit, stage_row_name, "Completed", based_on_modified, notes=notes)


@frappe.whitelist()
def record_labour_entry(
	development_unit: str,
	stage: str,
	start_time: str,
	end_time: str | None = None,
	hours: float | None = None,
	labour_type: str | None = None,
	employee: str | None = None,
	notes: str | None = None,
) -> dict:
	du = _get_unit(development_unit)
	du.append(
		"labour_entries",
		{
			"stage": stage,
			"user": frappe.session.user,
			"start_time": start_time,
			"end_time": end_time,
			"hours": hours,
			"labour_type": labour_type,
			"employee": employee,
			"notes": notes,
		},
	)
	du.save(ignore_permissions=True)
	return {"development_unit": du.name, "modified": str(du.modified)}


@frappe.whitelist()
def record_material_usage(
	development_unit: str,
	item: str,
	actual_quantity: float,
	waste_quantity: float | None = None,
	warehouse: str | None = None,
	notes: str | None = None,
) -> dict:
	du = _get_unit(development_unit)
	du.append(
		"material_usage",
		{
			"item": item,
			"actual_quantity": actual_quantity,
			"waste_quantity": waste_quantity,
			"warehouse": warehouse,
			"notes": notes,
		},
	)
	du.save(ignore_permissions=True)
	return {"development_unit": du.name, "modified": str(du.modified)}


@frappe.whitelist()
def add_issue(
	development_unit: str,
	issue_type: str,
	description: str,
	severity: str | None = None,
	stage_found: str | None = None,
	customer_visible: bool = False,
) -> dict:
	du = _get_unit(development_unit)
	du.append(
		"issues",
		{
			"issue_type": issue_type,
			"description": description,
			"severity": severity,
			"stage_found": stage_found,
			"customer_visible": customer_visible,
			"status": "Open",
		},
	)
	du.save(ignore_permissions=True)
	return {"development_unit": du.name, "modified": str(du.modified)}


@frappe.whitelist()
def add_evidence(
	development_unit: str,
	stage: str,
	file_url: str,
	evidence_type: str,
	notes: str | None = None,
	customer_visible: bool = False,
) -> dict:
	"""Metadata-only step of the two-phase evidence upload: the binary file
	is expected to already exist (uploaded separately via Frappe's standard
	`upload_file` endpoint), and this just links it to the unit/stage. Kept
	separate from the upload itself so this call stays small and fast
	through the normal JSON push pipeline, while the slow/flaky binary
	transfer gets its own retry loop on the client.
	"""
	du = _get_unit(development_unit)
	du.append(
		"evidence",
		{
			"stage": stage,
			"file": file_url,
			"evidence_type": evidence_type,
			"captured_by": frappe.session.user,
			"captured_on": now_datetime(),
			"notes": notes,
			"customer_visible": customer_visible,
		},
	)
	du.save(ignore_permissions=True)
	return {"development_unit": du.name, "modified": str(du.modified)}
