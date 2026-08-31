# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

from fitzgerald_kitchens.workbook_import.import_messages import (
	format_import_summary,
	format_validation_summary,
	validate_template_options,
)
from fitzgerald_kitchens.workbook_import.orchestrator import (
	append_log_to_doc,
	run_full_workbook_import,
	run_quantity_only_import,
	validate_full_workbook,
	validate_quantity_only,
)
from fitzgerald_kitchens.workbook_import.parser import WorkbookParseError


def validate_import(import_name: str) -> dict:
	doc = frappe.get_doc("Development Workbook Import", import_name)
	doc.import_status = "Validating"
	doc.error_log = ""
	doc.import_summary = ""
	doc.import_log = []
	doc.site_count = 0
	doc.unit_count = 0
	doc.subunit_count = 0
	doc.configuration_count = 0
	doc.manifest_count = 0
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	try:
		if not doc.import_file:
			raise WorkbookParseError(frappe._("Import File is required."))
		if not doc.company:
			raise WorkbookParseError(frappe._("Company is required."))
		validate_template_options(doc)

		if doc.import_mode == "Quantity Only":
			errors, preview = validate_quantity_only(doc)
		else:
			_file_url = (doc.import_file or "").lower()
			if not _file_url.endswith(".xlsx"):
				raise WorkbookParseError(frappe._("Full workbook import requires an .xlsx file."))
			errors, preview = validate_full_workbook(doc)

		if errors:
			doc.import_status = "Failed"
			doc.error_log = "\n".join(errors)
			doc.import_summary = ""
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			return {"ok": False, "errors": errors, "preview": preview}

		doc.import_status = "Ready"
		doc.site_count = preview.get("site_count", 0)
		doc.unit_count = preview.get("plot_count", 0)
		doc.subunit_count = preview.get("unit_project_count", 0)
		doc.configuration_count = preview.get("configuration_count", 0)
		doc.manifest_count = preview.get("manifest_count", 0)
		doc.error_log = ""
		doc.import_summary = format_validation_summary(preview)
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"ok": True, "preview": preview}

	except WorkbookParseError as exc:
		doc.import_status = "Failed"
		doc.error_log = str(exc)
		doc.import_summary = ""
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"ok": False, "errors": [str(exc)]}
	except Exception:
		doc.import_status = "Failed"
		doc.error_log = frappe.get_traceback()
		doc.import_summary = ""
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		raise


def run_import(import_name: str) -> None:
	doc = frappe.get_doc("Development Workbook Import", import_name)
	if doc.import_status != "Ready":
		frappe.throw(frappe._("Import status must be Ready. Validate the file first."))

	doc.import_status = "Importing"
	doc.import_log = []
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	try:
		if doc.import_mode == "Quantity Only":
			stats = run_quantity_only_import(doc)
		else:
			stats = run_full_workbook_import(doc)

		append_log_to_doc(doc, stats)

		from fitzgerald_kitchens.workbook_import.parser import parse_workbook_file
		from fitzgerald_kitchens.workbook_import.quantity_sheet import parse_quantity_sheet
		from fitzgerald_kitchens.workbook_import.scope import collect_site_type_scopes, count_unique_sites
		from fitzgerald_kitchens.workbook_import.workbook_reader import WorkbookReader

		if doc.import_mode == "Full Workbook":
			reader = WorkbookReader(doc.import_file)
			reader.load()
			quantity_rows = parse_quantity_sheet(reader)
		else:
			from fitzgerald_kitchens.workbook_import.naming import apply_site_scoped_configuration_codes

			quantity_rows = parse_workbook_file(doc.import_file)
			for row in quantity_rows:
				row["_unit_type"] = (row.get("configuration_code") or "").strip()
			apply_site_scoped_configuration_codes(quantity_rows)

		doc.site_count = count_unique_sites(quantity_rows)
		doc.unit_count = len(quantity_rows)
		doc.subunit_count = stats.units_created + stats.units_updated
		doc.configuration_count = len(collect_site_type_scopes(quantity_rows))
		doc.manifest_count = stats.manifests_created + stats.manifests_updated
		doc.import_status = "Completed"
		doc.error_log = ""
		template_label = doc.project_template if doc.generate_tasks_from_template else ""
		doc.import_summary = format_import_summary(stats, template_label=template_label)
		doc.save(ignore_permissions=True)
		frappe.db.commit()

	except WorkbookParseError as exc:
		doc.import_status = "Failed"
		doc.error_log = str(exc)
		doc.import_summary = ""
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		raise
	except Exception:
		doc.import_status = "Failed"
		doc.error_log = frappe.get_traceback()
		doc.import_summary = ""
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		raise


def enqueue_import(import_name: str) -> None:
	frappe.enqueue(
		"fitzgerald_kitchens.workbook_import.runner.run_import",
		queue="long",
		import_name=import_name,
		now=frappe.in_test,
	)
