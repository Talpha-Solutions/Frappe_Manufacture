# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE

UNIT_SNAPSHOT_SCOPE = "Unit Snapshot"


def is_unit_snapshot_manifest(manifest_name: str | None) -> bool:
	if not manifest_name:
		return False
	return (
		frappe.db.get_value("Manifest", manifest_name, "scope") == UNIT_SNAPSHOT_SCOPE
	)


def project_has_unit_snapshot_manifest(project_name: str) -> bool:
	manifest_name = frappe.db.get_value("Project", project_name, "fk_effective_manifest")
	return is_unit_snapshot_manifest(manifest_name)


def _next_unit_manifest_code(project_name: str) -> str:
	base = f"{project_name}-Manifest"
	if not frappe.db.exists("Manifest", base):
		return base

	counter = 2
	while frappe.db.exists("Manifest", f"{project_name}-Manifest-{counter}"):
		counter += 1
	return f"{project_name}-Manifest-{counter}"


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
	new_code = _next_unit_manifest_code(project_doc.name)

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
