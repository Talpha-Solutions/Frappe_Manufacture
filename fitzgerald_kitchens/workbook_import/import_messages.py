# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

from fitzgerald_kitchens.workbook_import.import_log import ImportRunStats
from fitzgerald_kitchens.workbook_import.parser import WorkbookParseError

LEGACY_SUCCESS_MARKERS = (
	"Import completed",
	"Validation passed",
	"Manifests created:",
	"PUC records created:",
)


def is_legacy_success_message(text: str | None) -> bool:
	text = (text or "").strip()
	if not text:
		return False
	return any(marker in text for marker in LEGACY_SUCCESS_MARKERS)


def normalize_import_log_fields(doc) -> bool:
	"""Move mistaken success text from error_log to import_summary; clear error_log."""
	if doc.import_status == "Failed":
		return False

	error_log = (getattr(doc, "error_log", None) or "").strip()
	if not error_log or not is_legacy_success_message(error_log):
		return False

	if not (getattr(doc, "import_summary", None) or "").strip():
		doc.import_summary = error_log
	doc.error_log = ""
	return True


def _doc_val(doc, field: str, default=None):
	if hasattr(doc, "get") and callable(doc.get):
		return doc.get(field, default)
	return getattr(doc, field, default)


def project_factory_kwargs(doc) -> dict:
	return {
		"company": doc.company,
		"create_missing_developer": bool(doc.create_missing_developer),
		"generate_tasks_from_template": bool(_doc_val(doc, "generate_tasks_from_template")),
		"project_template": _doc_val(doc, "project_template") or "",
	}


def validate_template_options(doc) -> None:
	if _doc_val(doc, "generate_tasks_from_template") and not _doc_val(doc, "project_template"):
		raise WorkbookParseError(
			frappe._("Project Template is required when Generate Tasks from Template is enabled.")
		)


def format_validation_summary(preview: dict) -> str:
	return frappe._(
		"Validation passed.\n"
		"• {0} site project(s)\n"
		"• {1} configuration(s) (site and type)\n"
		"• {2} apartment row(s)\n"
		"• {3} unit project(s) planned\n"
		"• {4} manifest(s) planned"
	).format(
		preview.get("site_count", 0),
		preview.get("configuration_count", 0),
		preview.get("plot_count", 0),
		preview.get("unit_project_count", 0),
		preview.get("manifest_count", 0),
	)


def format_import_summary(stats: ImportRunStats, *, template_label: str = "") -> str:
	lines = [
		frappe._("Import completed successfully."),
		frappe._("• Sites: {0} created, {1} updated").format(
			stats.sites_created, stats.sites_updated
		),
		frappe._("• Unit projects: {0} created, {1} updated").format(
			stats.units_created, stats.units_updated
		),
		frappe._("• Configurations: {0} created, {1} updated").format(
			stats.configurations_created, stats.configurations_updated
		),
		frappe._("• Manifests: {0} created, {1} updated").format(
			stats.manifests_created, stats.manifests_updated
		),
	]
	if template_label:
		lines.append(
			frappe._("• Tasks from template {0}: {1} unit project(s) (Site excluded)").format(
				template_label,
				stats.tasks_from_template_applied,
			)
		)
	return "\n".join(lines)
