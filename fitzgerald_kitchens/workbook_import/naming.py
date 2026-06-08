# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import re

import frappe

_INVALID_SCOPE_CHARS = re.compile(r"[\|/\\]+")

# Label for Quantity Sheet Number column in display titles (was "Apt").
UNIT_LOCATION_PREFIX = "Unit"


def format_unit_location_label(house_number: str) -> str:
	number = str(house_number or "").strip()
	if not number:
		return UNIT_LOCATION_PREFIX
	return f"{UNIT_LOCATION_PREFIX} {number}"


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


def build_vanity_manifest_code(unit_type: str, site_name: str) -> str:
	return f"{(unit_type or '').strip()}-Vanity-Manifest-{normalize_site_scope(site_name)}"


def build_pantry_manifest_code(unit_type: str, site_name: str) -> str:
	return f"{(unit_type or '').strip()}-Pantry-Manifest-{normalize_site_scope(site_name)}"


def build_unit_project_name(site_name: str, house_number: str, project_type: str) -> str:
	return f"{format_unit_location_label(house_number)} | {project_type} | {site_name.strip()}"


def unit_context_label_for_project(project) -> str:
	"""Full unit label e.g. Unit 11 | Kitchen | The Lane MOCKSITE."""
	if isinstance(project, str):
		project = frappe.get_doc("Project", project)
	elif not hasattr(project, "get"):
		project = frappe._dict(project)

	if project.get("project_name") and project.get("fk_parent_project"):
		return project.project_name.strip()

	if project.get("fk_parent_project") and project.get("fk_house_number"):
		site_name = frappe.db.get_value("Project", project.fk_parent_project, "project_name") or ""
		return build_unit_project_name(site_name, project.fk_house_number, project.project_type or "")

	return ""


def format_task_subject_with_unit_context(subject: str, unit_context: str) -> str:
	subject = (subject or "").strip()
	unit_context = (unit_context or "").strip()
	if not unit_context:
		return subject
	suffix = f" - {unit_context}"
	if subject.endswith(suffix):
		return subject
	return f"{subject}{suffix}"


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
