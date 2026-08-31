# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe

from fitzgerald_kitchens.workbook_import.import_log import ImportRunStats, WorkbookImportLogEntry
from fitzgerald_kitchens.workbook_import.import_messages import project_factory_kwargs, validate_template_options
from fitzgerald_kitchens.workbook_import.manifest_importer import (
	ensure_configuration_stubs,
	import_manifests,
	validate_manifest_items,
	validate_manifest_links,
)
from fitzgerald_kitchens.workbook_import.naming import apply_site_scoped_configuration_codes
from fitzgerald_kitchens.workbook_import.parser import WorkbookParseError, parse_workbook_file
from fitzgerald_kitchens.workbook_import.project_factory import WorkbookProjectFactory
from fitzgerald_kitchens.workbook_import.quantity_sheet import parse_quantity_sheet
from fitzgerald_kitchens.workbook_import.manifest_requirements import (
	count_planned_manifests,
	requirements_by_type,
)
from fitzgerald_kitchens.workbook_import.scope import (
	collect_site_type_scopes,
	count_unique_sites,
	unique_unit_types,
)
from fitzgerald_kitchens.workbook_import.spec_importer import import_spec_configurations
from fitzgerald_kitchens.workbook_import.type_mapping import (
	discover_manifest_sheet_mappings,
	validation_errors_for_manifest_sheets,
)
from fitzgerald_kitchens.workbook_import.validator import validate_workbook_rows
from fitzgerald_kitchens.workbook_import.workbook_reader import WorkbookReader


def validate_full_workbook(doc) -> tuple[list[str], dict[str, Any]]:
	errors: list[str] = []
	preview: dict[str, Any] = {}

	try:
		validate_template_options(doc)
		reader = WorkbookReader(doc.import_file)
		reader.load()

		if not reader.has_sheet("Spec Sheet"):
			errors.append("Missing sheet: Spec Sheet")

		quantity_rows = parse_quantity_sheet(reader)
		scopes = collect_site_type_scopes(quantity_rows)
		manifest_mappings = discover_manifest_sheet_mappings(reader)
		required_by_type = requirements_by_type(quantity_rows)
		errors.extend(validation_errors_for_manifest_sheets(manifest_mappings, required_by_type))
		errors.extend(
			validate_manifest_items(
				reader=reader,
				scopes=scopes,
				quantity_rows=quantity_rows,
				manifest_mappings=manifest_mappings,
			)
		)

		qty_errors, qty_preview = validate_workbook_rows(
			quantity_rows,
			create_missing_developer=bool(doc.create_missing_developer),
			validate_configuration_exists=False,
		)
		errors.extend(qty_errors)

		preview = {
			"site_type_scopes": len(scopes),
			"type_count": len(unique_unit_types(scopes)),
			"manifest_count": count_planned_manifests(quantity_rows, scopes),
			"configuration_count": len(scopes),
			"plot_count": qty_preview.get("plot_count", 0),
			"site_count": count_unique_sites(quantity_rows),
			"unit_project_count": qty_preview.get("unit_project_count", 0),
			"sheets": reader.sheet_names(),
		}
	except WorkbookParseError as exc:
		errors.append(str(exc))
	except Exception as exc:
		errors.append(str(exc))

	return errors, preview


def run_full_workbook_import(doc) -> ImportRunStats:
	reader = WorkbookReader(doc.import_file)
	reader.load()

	quantity_rows = parse_quantity_sheet(reader)
	scopes = collect_site_type_scopes(quantity_rows)
	manifest_mappings = discover_manifest_sheet_mappings(reader)
	stats = ImportRunStats()

	ensure_configuration_stubs(scopes, stats)
	import_manifests(
		reader=reader,
		scopes=scopes,
		quantity_rows=quantity_rows,
		manifest_mappings=manifest_mappings,
		strict_item_validation=bool(doc.strict_item_validation),
		stats=stats,
	)
	import_spec_configurations(
		reader=reader,
		scopes=scopes,
		quantity_rows=quantity_rows,
		unit_types=unique_unit_types(scopes),
		stats=stats,
	)

	link_errors = validate_manifest_links(scopes, quantity_rows)
	if link_errors:
		raise WorkbookParseError("\n".join(link_errors))

	factory = WorkbookProjectFactory(**project_factory_kwargs(doc), run_stats=stats)
	factory.import_rows(quantity_rows)

	return stats


def append_log_to_doc(doc, stats: ImportRunStats) -> None:
	doc.import_log = []
	for entry in stats.log:
		doc.append(
			"import_log",
			{
				"phase": entry.phase,
				"document_type": entry.document_type,
				"document_code": entry.document_code,
				"row_number": entry.row_number,
				"developer": entry.developer,
				"site_name": entry.site_name,
				"house_number": entry.house_number,
				"project_type": entry.project_type,
				"action": entry.action,
				"project": entry.project,
				"message": entry.message,
			},
		)


def validate_quantity_only(doc) -> tuple[list[str], dict[str, Any]]:
	validate_template_options(doc)
	rows = parse_workbook_file(doc.import_file)
	for row in rows:
		row["_unit_type"] = (row.get("configuration_code") or "").strip()
	apply_site_scoped_configuration_codes(rows)
	return validate_workbook_rows(
		rows, create_missing_developer=bool(doc.create_missing_developer)
	)


def run_quantity_only_import(doc) -> ImportRunStats:
	rows = parse_workbook_file(doc.import_file)
	for row in rows:
		row["_unit_type"] = (row.get("configuration_code") or "").strip()
	apply_site_scoped_configuration_codes(rows)

	stats = ImportRunStats()
	factory = WorkbookProjectFactory(**project_factory_kwargs(doc), run_stats=stats)
	factory.import_rows(rows)

	for entry in factory.stats.log:
		stats.log.append(
			WorkbookImportLogEntry(
				phase="Quantity",
				document_type="Project",
				document_code="",
				action=entry.action,
				row_number=entry.row_number,
				developer=entry.developer,
				site_name=entry.site_name,
				house_number=entry.house_number,
				project_type=entry.project_type,
				project=entry.project,
				message=entry.message,
			)
		)
	stats.sites_created = factory.stats.sites_created
	stats.sites_updated = factory.stats.sites_updated
	stats.units_created = factory.stats.units_created
	stats.units_updated = factory.stats.units_updated
	stats.configurations_linked = factory.stats.configurations_linked

	return stats
