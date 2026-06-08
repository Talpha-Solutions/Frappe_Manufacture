# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE

UNIT_SNAPSHOT_SCOPE = "Unit Snapshot"
PROJECT_TEMPLATE_SCOPE = "Project Template"


def is_unit_snapshot_manifest(manifest_name: str | None) -> bool:
	if not manifest_name:
		return False
	return (
		frappe.db.get_value("Manifest", manifest_name, "scope") == UNIT_SNAPSHOT_SCOPE
	)


def project_has_unit_snapshot_manifest(project_name: str) -> bool:
	manifest_name = frappe.db.get_value("Project", project_name, "fk_effective_manifest")
	return is_unit_snapshot_manifest(manifest_name)


def _root_template_manifest_code(source) -> str:
	"""Return the workbook template manifest code (e.g. T1-Manifest-The Lane MOCKSITE)."""
	manifest = source
	seen = {manifest.name}

	while manifest.scope != PROJECT_TEMPLATE_SCOPE and manifest.get("based_on_manifest"):
		if manifest.based_on_manifest in seen:
			break
		seen.add(manifest.based_on_manifest)
		manifest = frappe.get_doc("Manifest", manifest.based_on_manifest)

	return manifest.manifest_code


def _next_unit_manifest_code(template_code: str, project_id: str) -> str:
	"""e.g. T1-Manifest-The Lane MOCKSITE-UNIT-KIT-00011"""
	base = f"{template_code.strip()}-{project_id.strip()}"
	if not frappe.db.exists("Manifest", base):
		return base

	counter = 2
	while frappe.db.exists("Manifest", f"{base}-{counter}"):
		counter += 1
	return f"{base}-{counter}"


@frappe.whitelist()
def amend_effective_manifest(project: str) -> str:
	"""Duplicate the project's effective manifest as an editable unit snapshot."""
	project_doc = frappe.get_doc("Project", project)
	project_doc.check_permission("write")
	frappe.has_permission("Manifest", ptype="create", throw=True)

	if project_doc.project_type == SITE_PROJECT_TYPE:
		frappe.throw(_("Amend Effective Manifest is only available for unit projects."))

	source_name = project_doc.get("fk_effective_manifest")
	if not source_name:
		frappe.throw(_("Set Effective Manifest on the Unit tab first."))

	source = frappe.get_doc("Manifest", source_name)
	template_code = _root_template_manifest_code(source)
	new_code = _next_unit_manifest_code(template_code, project_doc.name)

	amended = frappe.copy_doc(source)
	amended.manifest_code = new_code
	amended.scope = UNIT_SNAPSHOT_SCOPE
	amended.based_on_manifest = source.name
	amended.insert(ignore_permissions=True)

	frappe.db.set_value(
		"Project",
		project_doc.name,
		"fk_effective_manifest",
		amended.name,
		update_modified=True,
	)

	return amended.name
