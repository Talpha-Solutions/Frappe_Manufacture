# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import re

import frappe

_INVALID_SCOPE_CHARS = re.compile(r"[\|/\\]+")

# Short label in unit project_name (Quantity Sheet Number column value).
UNIT_LOCATION_PREFIX = "Apt"


def normalize_site_scope(site_name: str) -> str:
	site_name = (site_name or "").strip()
	if not site_name:
		frappe.throw(frappe._("Site name (Quantity Sheet Name column) is required."))
	cleaned = _INVALID_SCOPE_CHARS.sub("-", site_name).strip()
	if not cleaned:
		frappe.throw(frappe._("Site name '{0}' is invalid after normalization.").format(site_name))
	return cleaned


def build_configuration_code(unit_type: str, site_name: str) -> str:
	unit_type = (unit_type or "").strip()
	site = normalize_site_scope(site_name)
	if not unit_type:
		frappe.throw(frappe._("Unit type is required for configuration code."))
	return f"{unit_type}-{site}"


def build_configuration_display_name(unit_type: str, site_name: str) -> str:
	return f"{unit_type} {normalize_site_scope(site_name)}"


def build_kitchen_manifest_code(unit_type: str, site_name: str) -> str:
	return f"{(unit_type or '').strip()}-Manifest-{normalize_site_scope(site_name)}"


def build_robe_manifest_code(unit_type: str, site_name: str) -> str:
	return f"{(unit_type or '').strip()}-Robe-Manifest-{normalize_site_scope(site_name)}"


def build_unit_project_name(site_name: str, house_number: str, project_type: str) -> str:
	return f"{site_name.strip()} | {UNIT_LOCATION_PREFIX} {house_number} | {project_type}"


def apply_site_scoped_configuration_codes(rows: list[dict]) -> None:
	"""Set configuration_code on each row from Type + Quantity Sheet Name (site)."""
	for row in rows:
		site_name = (row.get("site_name") or "").strip()
		unit_type = (row.get("_unit_type") or "").strip()
		if not unit_type:
			raw = (row.get("configuration_code") or "").strip()
			if "-" in raw and site_name and raw.endswith(site_name):
				continue
			unit_type = raw.split("-", 1)[0].strip() if raw else ""
		if unit_type and site_name:
			row["configuration_code"] = build_configuration_code(unit_type, site_name)
