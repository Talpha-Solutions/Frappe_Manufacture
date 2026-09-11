# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Merges the `offline_sync_operations` hook every installed app can define
in its own `hooks.py`, so this engine never needs to know about any
particular app's doctypes or business logic — it only knows how to look up
"this operation name resolves to this whitelisted function".

A consuming app declares, in its own hooks.py:

    offline_sync_operations = {
        "task.complete_task": {
            "method": "my_app.my_module.complete_task",
            "target_doctype": "Task",
            "target_name_field": "task",
        },
    }

Frappe's hook loader merges dict-shaped hooks recursively across every
installed app (the same mechanism `doc_events` uses), which means each leaf
value (`method`, `target_doctype`, `target_name_field`) comes back as a list
of contributions rather than a single value — one entry per app that
declared it. In the normal case exactly one app declares any given
operation name, so we take the last contribution when more than one exists
(consistent with how Frappe resolves other same-key hook overrides: later
app load order wins).
"""

import frappe


def _unwrap(value):
	# Frappe's hook loader wraps every leaf of a dict-shaped hook in a list
	# (the same mechanism `doc_events` uses) so multiple apps can contribute
	# to the same key without clobbering each other. Queried per single app
	# (see below) there is only ever one contribution, so [0] is exact.
	if isinstance(value, list):
		return value[0] if value else None
	return value


def get_all_operations() -> dict:
	"""Every installed app's own `offline_sync_operations` hook, tagged with
	which app declared each entry. Queried per-app (not via the merged
	all-apps call) so `app_name` is known exactly rather than guessed.
	"""
	merged = {}
	for app in frappe.get_installed_apps():
		raw = frappe.get_hooks("offline_sync_operations", app_name=app) or {}
		for operation_name, config in raw.items():
			merged[operation_name] = {
				"method": _unwrap(config.get("method")),
				"target_doctype": _unwrap(config.get("target_doctype")),
				"target_name_field": _unwrap(config.get("target_name_field")),
				"app_name": app,
			}
	return merged


def get_operation(operation: str) -> dict:
	config = get_all_operations().get(operation)
	if not config or not config.get("method"):
		frappe.throw(f"Unknown offline sync operation: {operation}")
	return config


def resolve_target_name(operation: str, payload: dict) -> str | None:
	config = get_operation(operation)
	field = config.get("target_name_field")
	if not field:
		return None
	return payload.get(field)
