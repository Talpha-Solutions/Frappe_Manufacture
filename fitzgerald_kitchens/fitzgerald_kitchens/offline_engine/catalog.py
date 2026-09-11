# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Labeled offline catalog: apps register specific offline items; admins
select only what they need in Offline Sync Settings.

Consuming app hooks.py example:

    offline_sync_catalog = {
        "fk.my_tasks": {
            "label": "My Tasks",
            "description": "Assigned tasks: complete and despatch",
            "route": "/offline_app",
            "pull_keys": ["tasks"],
            "operations": ["task.complete_task", "despatch.submit_despatch_material_request"],
            "ui_section": "tasks",
        },
    }
"""

from __future__ import annotations

import frappe


def _unwrap(value):
	if isinstance(value, list):
		return value[0] if value else None
	return value


def _unwrap_list(value):
	if value is None:
		return []
	if isinstance(value, list):
		# Frappe may wrap a list hook leaf oddly; flatten one level of list-wrapping
		if value and isinstance(value[0], list):
			return value[0]
		# Or each string wrapped: ["a"] from single contribution
		if value and all(isinstance(v, str) for v in value):
			return list(value)
		return value
	return [value]


def get_all_catalog() -> dict:
	"""Every installed app's `offline_sync_catalog`, keyed by item id."""
	merged = {}
	for app in frappe.get_installed_apps():
		raw = frappe.get_hooks("offline_sync_catalog", app_name=app) or {}
		for item_id, config in raw.items():
			if not isinstance(config, dict):
				continue
			merged[item_id] = {
				"item": item_id,
				"label": _unwrap(config.get("label")) or item_id,
				"description": _unwrap(config.get("description")) or "",
				"route": _unwrap(config.get("route")) or "",
				"kind": _unwrap(config.get("kind")) or "feature",
				"ui_section": _unwrap(config.get("ui_section")) or "",
				"pull_keys": _unwrap_list(config.get("pull_keys")),
				"operations": _unwrap_list(config.get("operations")),
				"ref_doctype": _unwrap(config.get("ref_doctype")) or "",
				"app_name": app,
			}
	return merged


def get_catalog_item(item: str) -> dict | None:
	return get_all_catalog().get(item)


def _settings():
	if not frappe.db.exists("DocType", "Offline Sync Settings"):
		return None
	return frappe.get_single("Offline Sync Settings")


def settings_enabled() -> bool:
	settings = _settings()
	return bool(settings and settings.enabled)


def is_item_enabled(item: str) -> bool:
	"""True when Offline Sync is on and this catalog item is selected + enabled.

	`generic.doctypes` is also treated as enabled when DocType rows are configured,
	so /offline works without a manual pack pick (Settings auto-ensures the pack on save).
	"""
	settings = _settings()
	if not settings or not settings.enabled:
		return False
	for row in settings.features or []:
		key = _normalize_item_key(row.feature)
		if key == item and row.enabled:
			return True
	if item == "generic.doctypes" and any(r.ref_doctype for r in (settings.doctypes or [])):
		return True
	return False


def list_enabled_items(app_name: str | None = None) -> list[dict]:
	"""Enabled catalog items (optional filter by owning app)."""
	registry = get_all_catalog()
	settings = _settings()
	if not settings or not settings.enabled:
		return []

	out = []
	for row in settings.features or []:
		if not row.enabled or not row.feature:
			continue
		key = _normalize_item_key(row.feature)
		meta = registry.get(key) or {}
		if app_name and meta.get("app_name") != app_name:
			continue
		out.append(
			{
				"item": key,
				"label": row.label or meta.get("label") or key,
				"description": row.description or meta.get("description") or "",
				"route": row.route or meta.get("route") or "",
				"kind": meta.get("kind") or "feature",
				"ui_section": meta.get("ui_section") or "",
				"pull_keys": meta.get("pull_keys") or [],
				"operations": meta.get("operations") or [],
				"ref_doctype": meta.get("ref_doctype") or "",
				"app_name": row.app_name or meta.get("app_name") or "",
			}
		)
	return out


def enabled_pull_keys(app_name: str | None = None) -> set[str]:
	keys = set()
	for item in list_enabled_items(app_name=app_name):
		for k in item.get("pull_keys") or []:
			keys.add(k)
	return keys


def enabled_ui_sections(app_name: str | None = None) -> set[str]:
	sections = set()
	for item in list_enabled_items(app_name=app_name):
		if item.get("ui_section"):
			sections.add(item["ui_section"])
	return sections


def enabled_operations() -> set[str]:
	ops = set()
	for item in list_enabled_items():
		for op in item.get("operations") or []:
			ops.add(op)
	# Generic DocType mutations when generic catalog item is on or DocType rows exist
	settings = _settings()
	if settings and settings.enabled:
		generic_on = any(
			_normalize_item_key(row.feature) == "generic.doctypes" and row.enabled
			for row in (settings.features or [])
		)
		if generic_on or (settings.doctypes or []):
			ops.add("doc.insert")
			ops.add("doc.save")
	return ops


def is_operation_allowed(operation: str) -> bool:
	"""Whether a push operation may run under current Offline Sync Settings."""
	if not settings_enabled():
		# Settings off: allow named ops (legacy FK) but still run — catalogs are opt-in
		# When settings are disabled, catalog gating is inactive.
		return True
	allowed = enabled_operations()
	# If admin enabled Offline Sync but selected nothing that grants ops,
	# only allow ops that appear in enabled catalog (strict).
	if operation in allowed:
		return True
	# Operation not tied to any selected item
	return False


def any_item_enabled_for_app(app_name: str) -> bool:
	return bool(list_enabled_items(app_name=app_name))


def _normalize_item_key(value: str) -> str:
	if not value:
		return value
	if " — " in value:
		return value.split(" — ", 1)[0].strip()
	return value.strip()


# --- Backward-compatible aliases used by earlier feature-pack code ---


def get_all_features() -> dict:
	return get_all_catalog()


def get_feature(feature: str) -> dict | None:
	return get_catalog_item(feature)


def is_feature_enabled(feature: str) -> bool:
	return is_item_enabled(feature)


def list_enabled_features() -> list[dict]:
	# Map to old shape expected by generic_pull
	return [
		{
			"feature": i["item"],
			"label": i["label"],
			"description": i["description"],
			"route": i["route"],
			"app_name": i["app_name"],
		}
		for i in list_enabled_items()
	]
