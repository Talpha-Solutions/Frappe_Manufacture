# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import json

import frappe

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.idempotency import run_idempotent


@frappe.whitelist()
def push(operations):
	"""Process a batch of offline-queued operations from any consuming app.

	`operations` is a list of {"client_uuid", "operation", "payload", "device_id"}.
	`operation` must be a name registered by some installed app's own
	`offline_sync_operations` hook. Each one is idempotent on its own
	`client_uuid` and committed independently, so one failing operation
	never rolls back the others in the same batch. Returns results in the
	same order as the input.
	"""

	if isinstance(operations, str):
		operations = json.loads(operations)

	results = []
	for op in operations or []:
		client_uuid = op.get("client_uuid")
		operation = op.get("operation")
		payload = op.get("payload") or {}
		device_id = op.get("device_id")

		if isinstance(payload, str):
			payload = json.loads(payload)

		if not client_uuid or not operation:
			results.append(
				{
					"client_uuid": client_uuid,
					"status": "Rejected",
					"error": "Both client_uuid and operation are required",
				}
			)
			continue

		results.append(run_idempotent(client_uuid, operation, payload, device_id))

	return results


@frappe.whitelist()
def status(device_id: str | None = None, app_name: str | None = None):
	"""Pending/success/failed/rejected counts for the current user, optionally
	scoped to one device and/or one consuming app."""

	filters = {"user": frappe.session.user}
	if device_id:
		filters["device_id"] = device_id
	if app_name:
		filters["app_name"] = app_name

	counts = {"pending": 0, "processing": 0, "success": 0, "failed": 0, "rejected": 0}
	statuses = frappe.get_all("Offline Sync Operation", filters=filters, pluck="status")
	for value in statuses:
		key = value.lower()
		counts[key] = counts.get(key, 0) + 1

	return counts
