# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from fitzgerald_kitchens.setup.project_qr_labels import expand_manifest_item_instances


def normalize_scanned_qr_text(qr_text: str) -> str:
	qr_text = (qr_text or "").strip()
	if not qr_text:
		return ""

	candidate = qr_text
	if "/" in qr_text:
		candidate = qr_text.rstrip("/").split("/")[-1]
		candidate = candidate.split("?")[0].strip()

	return candidate or qr_text


def _empty_label_state() -> dict:
	return {
		"total_labels": 0,
		"printed": 0,
		"scanned": 0,
		"outstanding": 0,
		"errors": 0,
		"manifest": None,
		"labels": [],
	}


def get_task_label_scan_state(task_name: str) -> dict:
	"""Build scanned / outstanding lists from project manifest QR labels."""
	project = frappe.db.get_value("Task", task_name, "project")
	if not project:
		return _empty_label_state()

	manifest_rows = expand_manifest_item_instances(project)
	if not manifest_rows:
		return _empty_label_state()

	scanned_codes = set(
		frappe.get_all(
			"Task Label Scan Log",
			filters={
				"task": task_name,
				"status": "Scanned",
				"item_instance_code": ["is", "set"],
			},
			pluck="item_instance_code",
			distinct=True,
		)
	)
	error_count = frappe.db.count("Task Label Scan Log", {"task": task_name, "status": "Error"})

	labels = []
	scanned = 0
	outstanding = 0

	for row in manifest_rows:
		code = row["item_instance_code"]
		if code in scanned_codes:
			status = "scanned"
			scanned += 1
		else:
			status = "outstanding"
			outstanding += 1

		labels.append(
			{
				"id": code,
				"item_code": row.get("item_code"),
				"item_name": row.get("item_name"),
				"status": status,
			}
		)

	total = len(manifest_rows)
	return {
		"project": project,
		"total_labels": total,
		"printed": total,
		"scanned": scanned,
		"outstanding": outstanding,
		"errors": error_count,
		"manifest": manifest_rows[0].get("manifest"),
		"labels": labels,
	}


def record_task_label_scan(task_name: str, qr_text: str) -> dict:
	"""Record a successful manifest label scan or an invalid QR error."""
	normalized = normalize_scanned_qr_text(qr_text)
	if not normalized:
		frappe.throw(_("Empty QR code"))

	task = frappe.db.get_value("Task", task_name, ["name", "project"], as_dict=True)
	if not task:
		frappe.throw(_("Task not found"), frappe.DoesNotExistError)
	if not task.project:
		frappe.throw(_("This task has no project linked"))

	manifest_rows = expand_manifest_item_instances(task.project)
	by_code = {row["item_instance_code"]: row for row in manifest_rows}

	if normalized not in by_code:
		_create_scan_log(
			task_name=task_name,
			project=task.project,
			status="Error",
			qr_text=qr_text,
		)
		state = get_task_label_scan_state(task_name)
		result = {
			"ok": False,
			"result": "error",
			"message": _("Unknown QR code — not part of this project's labels"),
			**state,
		}
		_publish_task_scan_update(task_name, result)
		return result

	if frappe.db.exists(
		"Task Label Scan Log",
		{"task": task_name, "item_instance_code": normalized, "status": "Scanned"},
	):
		state = get_task_label_scan_state(task_name)
		return {
			"ok": False,
			"result": "duplicate",
			"message": _("This label was already scanned"),
			**state,
		}

	row = by_code[normalized]
	_create_scan_log(
		task_name=task_name,
		project=task.project,
		status="Scanned",
		qr_text=qr_text,
		item_instance_code=normalized,
		item_code=row.get("item_code"),
		item_name=row.get("item_name"),
	)

	state = get_task_label_scan_state(task_name)
	result = {
		"ok": True,
		"result": "scanned",
		"message": _("Label scanned"),
		"item_instance_code": normalized,
		"scanned_by": frappe.session.user,
		**state,
	}
	_publish_task_scan_update(task_name, result)
	return result


def _publish_task_scan_update(task_name: str, payload: dict) -> None:
	frappe.publish_realtime(
		event="task_scan_update",
		message={"task": task_name, **payload},
		doctype="Task",
		docname=task_name,
		after_commit=True,
	)


def _create_scan_log(
	*,
	task_name: str,
	project: str,
	status: str,
	qr_text: str,
	item_instance_code: str | None = None,
	item_code: str | None = None,
	item_name: str | None = None,
) -> None:
	frappe.get_doc(
		{
			"doctype": "Task Label Scan Log",
			"task": task_name,
			"project": project,
			"status": status,
			"item_instance_code": item_instance_code,
			"item_code": item_code,
			"item_name": item_name,
			"qr_text": qr_text,
			"scanned_by": frappe.session.user,
			"scan_datetime": now_datetime(),
		}
	).insert(ignore_permissions=True)
