# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Generic pull + config for Offline Sync Settings–selected DocTypes."""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.settings import (
	form_fields_for_doctype,
	generic_offline_allowed,
	get_configured_rows,
	resolve_title_field,
	settings_enabled,
	title_for_doc,
)
from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.catalog import is_item_enabled
from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.features import list_enabled_features


@frappe.whitelist()
def get_offline_config():
	"""Config the /offline PWA needs: DocTypes, My Tasks pack, form field meta."""
	allowed = generic_offline_allowed()
	my_tasks = is_item_enabled("fk.my_tasks")
	doctypes = []

	if allowed:
		for row in get_configured_rows():
			doctype = row.ref_doctype
			if not frappe.has_permission(doctype, "read"):
				continue
			title_field = resolve_title_field(doctype, row.title_field)
			doctypes.append(
				{
					"doctype": doctype,
					"allow_create": 1 if row.allow_create else 0,
					"allow_write": 1 if row.allow_write else 0,
					"max_records": int(row.max_records or 200),
					"title_field": title_field,
					"fields": form_fields_for_doctype(doctype),
				}
			)

	return {
		"enabled": 1 if (allowed or my_tasks) else 0,
		"settings_enabled": 1 if settings_enabled() else 0,
		"generic_enabled": 1 if allowed else 0,
		"my_tasks_enabled": 1 if my_tasks else 0,
		"doctypes": doctypes,
		"features": list_enabled_features(),
		"server_time": str(now_datetime()),
	}


@frappe.whitelist()
def pull(since: str | None = None):
	"""Download documents for every settings-enabled DocType the user can read.

	`since` is an optional ISO datetime watermark (`modified > since`).
	Each DocType is capped by its Max Records setting.
	"""
	server_time = now_datetime()
	if not generic_offline_allowed():
		return {"enabled": 0, "docs": {}, "server_time": str(server_time)}

	docs_by_doctype = {}
	for row in get_configured_rows():
		doctype = row.ref_doctype
		if not frappe.has_permission(doctype, "read"):
			continue

		limit = int(row.max_records or 200)
		filters = {}
		if since:
			filters["modified"] = [">", since]

		# Prefer recent activity when over the cap (no since): order desc then
		# still return up to limit. With since, order asc so incremental catch-up
		# is stable.
		order_by = "modified asc" if since else "modified desc"

		names = frappe.get_list(
			doctype,
			filters=filters,
			pluck="name",
			order_by=order_by,
			limit_page_length=limit,
		)

		title_field = resolve_title_field(doctype, row.title_field)
		rows = []
		for name in names:
			if not frappe.has_permission(doctype, "read", doc=name):
				continue
			doc = frappe.get_doc(doctype, name)
			as_dict = doc.as_dict(no_nulls=False)
			as_dict["_title"] = title_for_doc(doctype, as_dict, title_field)
			rows.append(as_dict)

		docs_by_doctype[doctype] = rows

	return {
		"enabled": 1,
		"docs": docs_by_doctype,
		"server_time": str(server_time),
	}
