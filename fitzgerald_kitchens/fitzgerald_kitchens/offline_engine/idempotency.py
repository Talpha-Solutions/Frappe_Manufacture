# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.utils import now_datetime

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.registry import get_operation, resolve_target_name
from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.validation import OfflineConflict

# A "Processing" row older than this is assumed to belong to a crashed worker
# and is safe to retry rather than left stuck forever.
STALE_PROCESSING_MINUTES = 5


def run_idempotent(client_uuid: str, operation: str, payload: dict, device_id: str | None = None) -> dict:
	"""Run `operation` exactly once for `client_uuid`, replaying the cached
	result on any retry. One call = one committed transaction, independent of
	whatever else is in the surrounding push batch.
	"""

	payload = payload or {}
	existing = _get_existing(client_uuid)

	if existing:
		if existing.status == "Success":
			return _response(existing)
		if existing.status in ("Failed", "Rejected"):
			return _response(existing)
		if existing.status == "Processing" and not _is_stale(existing):
			return _response(existing)
		ledger = existing
	else:
		ledger = _create_ledger_row(client_uuid, operation, payload, device_id)

	ledger.status = "Processing"
	ledger.attempt_count = (ledger.attempt_count or 0) + 1
	ledger.save(ignore_permissions=True)
	frappe.db.commit()

	try:
		from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import is_operation_allowed, settings_enabled

		if settings_enabled() and not is_operation_allowed(operation):
			raise frappe.ValidationError(
				frappe._(
					"Operation {0} is not enabled in Offline Sync Settings. "
					"Add the matching Offline Item and save."
				).format(operation)
			)

		config = get_operation(operation)
		fn = frappe.get_attr(config["method"])
		result = fn(**payload)
		ledger.reload()
		ledger.status = "Success"
		ledger.server_result = _dumps(result)
		if isinstance(result, dict):
			if result.get("doctype"):
				ledger.target_doctype = result["doctype"]
			if result.get("name"):
				ledger.target_name = result["name"]
		ledger.processed_at = now_datetime()
		ledger.save(ignore_permissions=True)
		frappe.db.commit()
	except (frappe.ValidationError, frappe.PermissionError) as e:
		frappe.db.rollback()
		ledger.reload()
		ledger.status = "Rejected"
		ledger.error_message = str(e)
		if isinstance(e, OfflineConflict):
			ledger.server_result = _dumps({"conflict": True, "current_state": e.current_state})
		ledger.processed_at = now_datetime()
		ledger.save(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Offline sync operation failed: {operation}")
		ledger.reload()
		ledger.status = "Failed"
		ledger.error_message = str(e)
		ledger.processed_at = now_datetime()
		ledger.save(ignore_permissions=True)
		frappe.db.commit()

	return _response(ledger)


def _get_existing(client_uuid: str):
	if frappe.db.exists("Offline Sync Operation", client_uuid):
		return frappe.get_doc("Offline Sync Operation", client_uuid)
	return None


def _create_ledger_row(client_uuid, operation, payload, device_id):
	config = get_operation(operation)
	# Generic doc.insert / doc.save store the real DocType on the payload;
	# hook metadata target_doctype may be empty for those built-in ops.
	target_doctype = config.get("target_doctype") or payload.get("doctype")
	target_name = resolve_target_name(operation, payload) or payload.get("name")
	doc = frappe.get_doc(
		{
			"doctype": "Offline Sync Operation",
			"client_uuid": client_uuid,
			"operation": operation,
			"device_id": device_id,
			"user": frappe.session.user,
			"status": "Pending",
			"payload": _dumps(payload),
			"app_name": config.get("app_name"),
			"target_doctype": target_doctype,
			"target_name": target_name,
			"client_created_at": now_datetime(),
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


def _is_stale(ledger) -> bool:
	from frappe.utils import time_diff_in_seconds

	if not ledger.modified:
		return True
	return time_diff_in_seconds(now_datetime(), ledger.modified) > STALE_PROCESSING_MINUTES * 60


def _response(ledger) -> dict:
	result = None
	if ledger.server_result:
		try:
			result = json.loads(ledger.server_result)
		except ValueError:
			result = ledger.server_result

	return {
		"client_uuid": ledger.client_uuid,
		"status": ledger.status,
		"server_result": result,
		"error": ledger.error_message,
	}


def _dumps(value) -> str:
	try:
		return frappe.as_json(value)
	except TypeError:
		return json.dumps(str(value))
