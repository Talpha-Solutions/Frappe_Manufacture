# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import get_all_catalog, get_catalog_item, _normalize_item_key


class OfflineSyncSettings(Document):
	def validate(self):
		self._validate_doctypes()
		self._ensure_generic_pack_for_doctypes()
		self._validate_items()

	def _validate_doctypes(self):
		seen = set()
		for row in self.doctypes or []:
			if not row.ref_doctype:
				continue
			if row.ref_doctype in seen:
				frappe.throw(frappe._("DocType {0} is listed more than once").format(row.ref_doctype))
			seen.add(row.ref_doctype)

			meta = frappe.get_meta(row.ref_doctype)
			if meta.istable:
				frappe.throw(
					frappe._("{0} is a child table and cannot be synced offline on its own").format(
						row.ref_doctype
					)
				)
			if meta.issingle:
				frappe.throw(
					frappe._("{0} is a Single DocType and is not supported for offline sync").format(
						row.ref_doctype
					)
				)

			if row.max_records is not None and int(row.max_records) < 1:
				frappe.throw(frappe._("Max Records must be at least 1"))

	def _ensure_catalog_pack(self, item_key: str, fallback: dict | None = None):
		"""Ensure a catalog pack row exists and is enabled."""
		meta = get_catalog_item(item_key) or fallback or {}
		for row in self.features or []:
			if _normalize_item_key(row.feature or "") == item_key:
				row.feature = item_key
				row.enabled = 1
				row.label = meta.get("label") or row.label or item_key
				row.description = meta.get("description") or row.description or ""
				row.route = meta.get("route") or row.route or ""
				row.app_name = meta.get("app_name") or row.app_name or ""
				return

		self.append(
			"features",
			{
				"feature": item_key,
				"enabled": 1,
				"label": meta.get("label") or item_key,
				"description": meta.get("description") or "",
				"route": meta.get("route") or "",
				"app_name": meta.get("app_name") or "",
			},
		)

	def _ensure_generic_pack_for_doctypes(self):
		"""If any DocType is listed, ensure generic.doctypes pack is present and enabled."""
		has_doctypes = any(row.ref_doctype for row in (self.doctypes or []))
		if not has_doctypes:
			return

		self._ensure_catalog_pack(
			"generic.doctypes",
			{
				"label": "Generic DocTypes (/offline)",
				"description": "Built-in /offline PWA",
				"route": "/offline",
				"app_name": "fitzgerald_kitchens",
			},
		)

	def _ensure_doctype_row(self, doctype: str):
		for row in self.doctypes or []:
			if row.ref_doctype == doctype:
				return
		if not frappe.db.exists("DocType", doctype):
			return
		self.append(
			"doctypes",
			{
				"ref_doctype": doctype,
				"allow_create": 1,
				"allow_write": 1,
				"max_records": 200,
			},
		)

	def _validate_items(self):
		registry = get_all_catalog()
		seen = set()
		for row in self.features or []:
			if not row.feature:
				continue
			row.feature = _normalize_item_key(row.feature)

			if row.feature in seen:
				frappe.throw(frappe._("Offline item {0} is listed more than once").format(row.feature))
			seen.add(row.feature)

			meta = registry.get(row.feature)
			if not meta:
				frappe.throw(
					frappe._(
						"Unknown offline item: {0}. Register it in an app via offline_sync_catalog."
					).format(row.feature)
				)

			row.label = meta.get("label") or row.feature
			row.description = meta.get("description") or ""
			row.route = meta.get("route") or ""
			row.app_name = meta.get("app_name") or ""


@frappe.whitelist()
def get_feature_pack_options():
	"""Select options for Offline Sync Settings → App Offline Packs dropdown."""
	catalog = get_all_catalog()
	option_lines = []
	for item_id in sorted(catalog.keys(), key=lambda k: (catalog[k].get("label") or k).lower()):
		meta = catalog[item_id]
		option_lines.append(f"{item_id} — {meta.get('label') or item_id}")
	return {
		"options": "\n".join(option_lines),
		"features": list(catalog.values()),
	}


@frappe.whitelist()
def get_feature_details(feature: str):
	feature = _normalize_item_key(feature)
	meta = get_catalog_item(feature)
	if not meta:
		frappe.throw(frappe._("Unknown offline item: {0}").format(feature))
	return meta


@frappe.whitelist()
def get_enabled_catalog(app_name: str | None = None):
	"""Client helper: enabled labeled items (optionally for one app)."""
	from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import list_enabled_items, settings_enabled

	return {
		"enabled": 1 if settings_enabled() else 0,
		"items": list_enabled_items(app_name=app_name or None),
	}


@frappe.whitelist()
def ensure_phase1_defaults():
	"""Enable Offline Sync with Phase 1 DocTypes + My Tasks pack when FK is installed.

	Adds Customer + ToDo rows, ensures generic.doctypes, and fk.my_tasks when
	fitzgerald_kitchens is on the site. Idempotent.
	"""
	frappe.only_for("System Manager")

	doc = frappe.get_single("Offline Sync Settings")
	doc.enabled = 1
	doc._ensure_doctype_row("Customer")
	doc._ensure_doctype_row("ToDo")
	doc._ensure_catalog_pack(
		"generic.doctypes",
		{
			"label": "Generic DocTypes (/offline)",
			"description": "Built-in /offline PWA",
			"route": "/offline",
			"app_name": "fitzgerald_kitchens",
		},
	)
	if "fitzgerald_kitchens" in frappe.get_installed_apps():
		doc._ensure_catalog_pack(
			"fk.my_tasks",
			{
				"label": "My Tasks",
				"description": "Assigned tasks complete/despatch on /offline",
				"route": "/offline",
				"app_name": "fitzgerald_kitchens",
			},
		)
	doc.save()
	return {
		"enabled": 1,
		"doctypes": [r.ref_doctype for r in (doc.doctypes or []) if r.ref_doctype],
		"features": [r.feature for r in (doc.features or []) if r.feature and r.enabled],
	}
