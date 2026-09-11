# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Shared helpers for Offline Sync Settings → generic pull/mutations."""

from __future__ import annotations

import frappe

# Fieldtypes the built-in /offline form can edit in v1.
SIMPLE_FIELDTYPES = {
	"Data",
	"Link",
	"Select",
	"Date",
	"Datetime",
	"Time",
	"Check",
	"Text",
	"Small Text",
	"Long Text",
	"Text Editor",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Read Only",
}


def get_settings():
	"""Return Offline Sync Settings singleton (cached per request)."""
	return frappe.get_single("Offline Sync Settings")


def settings_enabled() -> bool:
	return bool(get_settings().enabled)


def get_configured_rows() -> list:
	"""Enabled settings rows keyed for iteration."""
	settings = get_settings()
	if not settings.enabled:
		return []
	return [row for row in (settings.doctypes or []) if row.ref_doctype]


def generic_offline_allowed() -> bool:
	"""Whether the built-in /offline PWA may load and pull.

	True when Settings is enabled and either DocType rows exist or the
	`generic.doctypes` catalog pack is enabled.
	"""
	from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import is_item_enabled

	return is_item_enabled("generic.doctypes")


def get_row_for_doctype(doctype: str):
	for row in get_configured_rows():
		if row.ref_doctype == doctype:
			return row
	return None


def assert_doctype_allowed(doctype: str, action: str):
	"""Raise ValidationError if doctype is not configured for offline action.

	action: 'read' | 'create' | 'write'
	"""
	if not settings_enabled():
		frappe.throw(frappe._("Offline Sync is disabled in Offline Sync Settings"), frappe.ValidationError)

	row = get_row_for_doctype(doctype)
	if not row:
		frappe.throw(
			frappe._("{0} is not enabled for offline sync").format(doctype),
			frappe.ValidationError,
		)

	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle:
		frappe.throw(
			frappe._("{0} is not supported for offline sync").format(doctype),
			frappe.ValidationError,
		)

	if action == "create" and not row.allow_create:
		frappe.throw(
			frappe._("Offline create is not allowed for {0}").format(doctype),
			frappe.ValidationError,
		)
	if action == "write" and not row.allow_write:
		frappe.throw(
			frappe._("Offline write is not allowed for {0}").format(doctype),
			frappe.ValidationError,
		)

	return row


def resolve_title_field(doctype: str, override: str | None = None) -> str:
	if override:
		return override
	meta = frappe.get_meta(doctype)
	return meta.title_field or "name"


def form_fields_for_doctype(doctype: str) -> list[dict]:
	"""Field metadata for the generic offline form."""
	meta = frappe.get_meta(doctype)
	fields = []
	for df in meta.fields:
		if df.fieldtype not in SIMPLE_FIELDTYPES:
			continue
		if df.hidden:
			continue
		fields.append(
			{
				"fieldname": df.fieldname,
				"label": df.label or df.fieldname,
				"fieldtype": df.fieldtype,
				"options": df.options,
				"reqd": 1 if df.reqd else 0,
				"in_list_view": 1 if df.in_list_view else 0,
				"read_only": 1 if df.read_only or df.fieldtype == "Read Only" else 0,
			}
		)
	return fields


def title_for_doc(doctype: str, doc: dict, title_field: str | None = None) -> str:
	tf = resolve_title_field(doctype, title_field)
	if tf and doc.get(tf):
		return str(doc.get(tf))
	return str(doc.get("name") or "")
