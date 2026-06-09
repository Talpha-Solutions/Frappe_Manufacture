# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import base64
import re
from urllib.parse import unquote

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from fitzgerald_kitchens.setup.project_qr_labels import expand_manifest_item_instances
from fitzgerald_kitchens.fitzgerald_kitchens.utils.qr_codes import generate_qr_png_bytes

LABEL_SCAN_TASK_TYPES = frozenset({"Assembly", "Despatch", "Delivery"})
LABEL_SCAN_TASK_TYPE_ALIASES = {
	"assembly": "Assembly",
	"despatch": "Despatch",
	"dispatch": "Despatch",
	"delivery": "Delivery",
}
COMPLETED_STATUS = "Completed"


def normalize_label_scan_task_type(task_type: str | None) -> str | None:
	if not task_type:
		return None
	clean = (task_type or "").strip()
	if clean in LABEL_SCAN_TASK_TYPES:
		return clean
	return LABEL_SCAN_TASK_TYPE_ALIASES.get(clean.lower())


def is_label_scan_task_type(task_type: str | None) -> bool:
	return normalize_label_scan_task_type(task_type) in LABEL_SCAN_TASK_TYPES


def normalize_scanned_qr_text(qr_text: str) -> str:
	qr_text = (qr_text or "").strip()
	if not qr_text:
		return ""

	# Hardware scanners often append CR/LF or other control characters.
	qr_text = re.sub(r"[\x00-\x1f\x7f]", "", qr_text).strip()

	candidate = qr_text
	if "/" in qr_text:
		candidate = qr_text.rstrip("/").split("/")[-1]
		candidate = candidate.split("?")[0].strip()

	candidate = unquote(candidate).strip()
	if candidate.lower().endswith(".png"):
		candidate = candidate[:-4].strip()

	return candidate or qr_text


def _canonical_code_key(code: str | None) -> str:
	return (code or "").strip().upper()


def _build_manifest_code_maps(manifest_rows: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
	by_code: dict[str, dict] = {}
	canonical_map: dict[str, str] = {}
	for row in manifest_rows:
		code = (row.get("item_instance_code") or "").strip()
		if not code:
			continue
		by_code[code] = row
		canonical_map[_canonical_code_key(code)] = code
	return by_code, canonical_map


def _resolve_manifest_code(
	normalized: str,
	by_code: dict[str, dict],
	canonical_map: dict[str, str],
) -> str | None:
	clean = (normalized or "").strip()
	if not clean:
		return None

	if clean in by_code:
		return clean

	canonical = _canonical_code_key(clean)
	if canonical in canonical_map:
		return canonical_map[canonical]

	suffix_matches = [
		code
		for code in by_code
		if _canonical_code_key(code).endswith(canonical) or canonical.endswith(_canonical_code_key(code))
	]
	if len(suffix_matches) == 1:
		return suffix_matches[0]

	return None


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


def _get_task_scan_meta(task_name: str) -> dict | None:
	task = frappe.db.get_value(
		"Task",
		task_name,
		["name", "project", "type", "status"],
		as_dict=True,
	)
	if task and task.type:
		task.type = normalize_label_scan_task_type(task.type) or task.type
	return task


def _get_manifest_rows_for_task(task_name: str, project: str, task_type: str | None = None) -> list[dict]:
	"""Each Assembly / Despatch / Delivery task uses the full project QR list."""
	del task_name, task_type
	return expand_manifest_item_instances(project)


def get_task_label_scan_state(task_name: str) -> dict:
	"""Build scanned / outstanding lists from project manifest QR labels for this task."""
	task = _get_task_scan_meta(task_name)
	if not task or not task.project:
		return _empty_label_state()

	manifest_rows = _get_manifest_rows_for_task(task_name, task.project, task.type)
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
		"project": task.project,
		"total_labels": total,
		"printed": total,
		"scanned": scanned,
		"outstanding": outstanding,
		"errors": error_count,
		"manifest": manifest_rows[0].get("manifest"),
		"labels": labels,
	}


def _scan_progress_percent(state: dict) -> float:
	total = state.get("total_labels") or 0
	if not total:
		return 0
	return flt((state.get("scanned") or 0) / total * 100, 2)


def _sync_task_progress_from_scan_state(task_name: str, state: dict) -> dict | None:
	task_type = normalize_label_scan_task_type(frappe.db.get_value("Task", task_name, "type"))
	if task_type not in LABEL_SCAN_TASK_TYPES:
		return None

	total = state.get("total_labels") or 0
	if not total:
		return None

	from fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer import _apply_task_update

	progress = _scan_progress_percent(state)
	if progress >= 100:
		progress = 100

	result = _apply_task_update(task_name, progress=progress)
	return {"progress": flt(result.get("progress")), "status": result.get("status")}


def _finalize_task_after_all_labels_scanned(task_name: str) -> dict | None:
	task_type = normalize_label_scan_task_type(frappe.db.get_value("Task", task_name, "type"))
	if task_type not in LABEL_SCAN_TASK_TYPES:
		return None

	from fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer import (
		finalize_task_after_all_labels_scanned,
	)

	return finalize_task_after_all_labels_scanned(task_name)


def _apply_scan_side_effects(task_name: str, state: dict) -> dict:
	side_effects = {
		"task_progress": None,
		"task_completed": False,
		"timer_started": False,
		"timer_stopped": False,
		"timesheet_submitted": False,
	}

	total = state.get("total_labels") or 0
	if not total:
		return side_effects

	if state.get("outstanding") == 0:
		finalize = _finalize_task_after_all_labels_scanned(task_name) or {}
		side_effects["task_completed"] = True
		side_effects["task_progress"] = 100
		side_effects["timer_stopped"] = bool(finalize.get("stopped"))
		side_effects["timesheet_submitted"] = bool(
			(finalize.get("timesheet_submit") or {}).get("submitted")
		)
		side_effects["task_update"] = finalize.get("task_update")
		side_effects["timesheet_submit"] = finalize.get("timesheet_submit")
		side_effects["timer"] = finalize
		mr_submit = _sync_despatch_material_request_side_effects(task_name, side_effects, submit=True)
		if mr_submit:
			side_effects["material_request_submit"] = mr_submit
		return side_effects

	from fitzgerald_kitchens.fitzgerald_kitchens.page.my_tasks.task_timer import (
		ensure_task_timer_started_for_scan,
	)

	timer_payload = ensure_task_timer_started_for_scan(task_name)
	if timer_payload:
		side_effects["timer_started"] = bool(timer_payload.get("timer_running"))
		side_effects["timer"] = timer_payload

	progress_update = _sync_task_progress_from_scan_state(task_name, state)
	if progress_update:
		side_effects["task_progress"] = progress_update.get("progress")

	_sync_despatch_material_request_side_effects(task_name, side_effects, submit=False)

	return side_effects


def _sync_despatch_material_request_side_effects(
	task_name: str, side_effects: dict, *, submit: bool
) -> dict | None:
	task_type = normalize_label_scan_task_type(frappe.db.get_value("Task", task_name, "type"))
	if task_type != "Despatch":
		return None

	from fitzgerald_kitchens.fitzgerald_kitchens.page.task_scan.despatch_material_request import (
		submit_despatch_material_request,
		sync_despatch_material_request,
	)

	try:
		if submit:
			result = submit_despatch_material_request(task_name)
		else:
			result = sync_despatch_material_request(task_name)
	except Exception as exc:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Despatch material request failed for {task_name}",
		)
		side_effects["material_request_error"] = str(exc)
		return None

	if result:
		side_effects["material_request"] = result.get("name") or result.get("new_mr")
		side_effects["material_request_updated"] = bool(result.get("updated"))
		if result.get("errors"):
			side_effects["material_request_warnings"] = result.get("errors")
		if result.get("skipped"):
			side_effects["material_request_skipped"] = result.get("reason")
	return result


def record_task_label_scan(task_name: str, qr_text: str) -> dict:
	"""Record a successful manifest label scan or an invalid QR error."""
	normalized = normalize_scanned_qr_text(qr_text)
	if not normalized:
		frappe.throw(_("Empty QR code"))

	task = _get_task_scan_meta(task_name)
	if not task:
		frappe.throw(_("Task not found"), frappe.DoesNotExistError)
	if not task.project:
		frappe.throw(_("This task has no project linked"))
	if not is_label_scan_task_type(task.type):
		frappe.throw(_("Label scanning is only available for Assembly, Despatch, and Delivery tasks"))
	if task.status == COMPLETED_STATUS:
		frappe.throw(_("This task is already completed"))

	manifest_rows = _get_manifest_rows_for_task(task_name, task.project, task.type)
	by_code, canonical_map = _build_manifest_code_maps(manifest_rows)

	resolved_code = _resolve_manifest_code(normalized, by_code, canonical_map)

	if not resolved_code:
		_create_scan_log(
			task_name=task_name,
			project=task.project,
			status="Error",
			qr_text=qr_text,
			item_instance_code=None,
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
		{"task": task_name, "item_instance_code": resolved_code, "status": "Scanned"},
	):
		state = get_task_label_scan_state(task_name)
		return {
			"ok": False,
			"result": "duplicate",
			"message": _("This label was already scanned"),
			**state,
		}

	row = by_code[resolved_code]
	_create_scan_log(
		task_name=task_name,
		project=task.project,
		status="Scanned",
		qr_text=qr_text,
		item_instance_code=resolved_code,
		item_code=row.get("item_code"),
		item_name=row.get("item_name"),
	)

	state = get_task_label_scan_state(task_name)
	side_effects = _apply_scan_side_effects(task_name, state)

	message = _("Label scanned")
	if side_effects.get("task_completed"):
		message = _("All labels scanned — timer stopped, timesheet submitted, task completed")

	result = {
		"ok": True,
		"result": "scanned",
		"message": message,
		"item_instance_code": resolved_code,
		"scanned_by": frappe.session.user,
		**side_effects,
		**state,
	}
	_publish_task_scan_update(task_name, result)
	return result


def _qr_base64_for_code(code: str | None) -> str | None:
	if not code:
		return None
	try:
		png = generate_qr_png_bytes(code.strip())
		return base64.b64encode(png).decode("ascii")
	except Exception:
		return None


@frappe.whitelist()
def get_task_label_scan_logs(task: str) -> dict:
	"""Return scan log rows and summary for the Task form tab."""
	if not frappe.db.exists("Task", task):
		frappe.throw(_("Task not found"), frappe.DoesNotExistError)
	if not frappe.has_permission("Task", doc=task, ptype="read"):
		frappe.throw(_("Not permitted to access this task"), frappe.PermissionError)

	state = get_task_label_scan_state(task)
	logs = frappe.get_all(
		"Task Label Scan Log",
		filters={"task": task},
		fields=[
			"name",
			"status",
			"item_instance_code",
			"item_code",
			"item_name",
			"qr_text",
			"scanned_by",
			"scan_datetime",
		],
		order_by="scan_datetime desc, creation desc",
		limit=500,
	)

	for log in logs:
		code = log.get("item_instance_code") or normalize_scanned_qr_text(log.get("qr_text") or "")
		log["qr_base64"] = _qr_base64_for_code(code)

	return {
		**state,
		"progress_percent": _scan_progress_percent(state),
		"logs": logs,
	}


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
