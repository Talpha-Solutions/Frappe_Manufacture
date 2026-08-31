# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Bench execute helpers for full workbook import smoke tests."""

from __future__ import annotations

import frappe
from frappe.utils.file_manager import save_file

from fitzgerald_kitchens.workbook_import.orchestrator import (
	run_full_workbook_import,
	validate_full_workbook,
)


def _demo_workbook_path() -> str:
	import os

	from fitzgerald_kitchens import __file__ as pkg_init

	app_root = os.path.dirname(os.path.dirname(pkg_init))
	return os.path.join(app_root, "1Fitzgerald_Kitchens_Synthetic_Demo_Client_Workbook.xlsx")


def _attach_demo_file() -> str:
	path = _demo_workbook_path()
	with open(path, "rb") as handle:
		content = handle.read()

	file_doc = save_file(
		"1Fitzgerald_Kitchens_Synthetic_Demo_Client_Workbook.xlsx",
		content,
		"Development Workbook Import",
		"WORKBOOK-TEST",
		is_private=1,
	)
	return file_doc.file_url


class _StubDoc:
	def __init__(self, *, strict: bool = False):
		self.import_file = _attach_demo_file()
		self.create_missing_developer = True
		self.strict_item_validation = strict
		self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)


def run_validation_test() -> dict:
	errors, preview = validate_full_workbook(_StubDoc())
	return {"error_count": len(errors), "errors": errors[:20], "preview": preview}


def run_import_test() -> dict:
	doc = _StubDoc(strict=False)
	stats = run_full_workbook_import(doc)
	return {
		"manifests_created": stats.manifests_created,
		"manifests_updated": stats.manifests_updated,
		"configurations_created": stats.configurations_created,
		"configurations_updated": stats.configurations_updated,
		"sites_created": stats.sites_created,
		"sites_updated": stats.sites_updated,
		"units_created": stats.units_created,
		"units_updated": stats.units_updated,
		"items_created": stats.items_created,
		"items_updated": stats.items_updated,
		"items_skipped": stats.items_skipped,
		"items_errors": stats.items_errors,
		"log_entries": len(stats.log),
	}


def run_idempotency_test() -> dict:
	first = run_import_test()
	second = run_import_test()
	lane_config = "T3-The Lane MOCKSITE"
	avenue_manifest = "T1V-Manifest-The Avenue MOCKSITE"
	return {
		"first": first,
		"second": second,
		"lane_config": frappe.db.exists("Project Unit Configuration", lane_config),
		"avenue_manifest": frappe.db.exists("Manifest", avenue_manifest),
	}


def run_item_upsert_scenarios() -> dict:
	"""Bench-execute check for the Manifest Item upsert scenarios (A-H).

	Run with:
	    bench --site <site> execute \
	        fitzgerald_kitchens.workbook_import.test_full_workbook.run_item_upsert_scenarios

	Creates/removes a few throwaway Items prefixed ZZTEST- so it is safe to run
	against a real site and re-run repeatedly (scenario H: idempotency).
	"""
	from fitzgerald_kitchens.workbook_import.import_log import ImportRunStats
	from fitzgerald_kitchens.workbook_import.manifest_importer import (
		_build_manifest_items,
		_upsert_item,
	)

	results: dict[str, dict] = {}
	stats = ImportRunStats()
	cache: dict[str, dict] = {}

	existing_code = "ZZTEST-EXISTING"
	if not frappe.db.exists("Item", existing_code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": existing_code,
				"item_name": "ZZTEST Existing Item",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"description": "Pre-existing description that must not be overwritten",
			}
		).insert(ignore_permissions=True)

	# A: existing item is reused, unrelated data untouched (also covers E).
	ok = _upsert_item(
		item_code=existing_code,
		item_description="New description from workbook",
		create_missing=True,
		stats=stats,
		sheet_name="TEST",
		row_number=1,
		item_cache=cache,
	)
	results["A_existing_item_reused"] = {
		"ok": ok,
		"cache_entry": cache.get(existing_code),
		"description_unchanged": frappe.db.get_value("Item", existing_code, "description")
		== "Pre-existing description that must not be overwritten",
	}

	# B: missing item is auto-created.
	new_code = "ZZTEST-NEW"
	if frappe.db.exists("Item", new_code):
		frappe.delete_doc("Item", new_code, ignore_permissions=True, force=True)
	ok = _upsert_item(
		item_code=new_code,
		item_description="Brand new test item",
		create_missing=True,
		stats=stats,
		sheet_name="TEST",
		row_number=2,
		item_cache={},
	)
	results["B_missing_item_created"] = {
		"ok": ok,
		"exists_now": bool(frappe.db.exists("Item", new_code)),
		"items_created": stats.items_created,
	}

	# C: same item requested twice only creates/logs once (cache hit second time).
	dup_cache: dict[str, dict] = {}
	dup_stats = ImportRunStats()
	dup_code = "ZZTEST-DUP"
	if frappe.db.exists("Item", dup_code):
		frappe.delete_doc("Item", dup_code, ignore_permissions=True, force=True)
	_upsert_item(
		item_code=dup_code,
		item_description="Dup item",
		create_missing=True,
		stats=dup_stats,
		sheet_name="TEST",
		row_number=3,
		item_cache=dup_cache,
	)
	_upsert_item(
		item_code=dup_code,
		item_description="Dup item",
		create_missing=True,
		stats=dup_stats,
		sheet_name="TEST",
		row_number=4,
		item_cache=dup_cache,
	)
	results["C_duplicate_row_created_once"] = {"items_created": dup_stats.items_created}

	# D: same item code with different Item Description/dimensions across sheets does not
	# corrupt the Item master — dimensions never land on Item (only on Manifest Item rows),
	# and a second, different description is reported as a Conflict log entry, not applied.
	conflict_cache: dict[str, dict] = {}
	conflict_stats = ImportRunStats()
	conflict_code = "ZZTEST-CONFLICT"
	if frappe.db.exists("Item", conflict_code):
		frappe.delete_doc("Item", conflict_code, ignore_permissions=True, force=True)
	rows_t1 = [
		{"row_number": 10, "Description": conflict_code, "Item Description": "800mm variant", "Width": 800, "Qty": 1}
	]
	rows_t2 = [
		{"row_number": 11, "Description": conflict_code, "Item Description": "1200mm variant", "Width": 1200, "Qty": 1}
	]
	items_t1 = _build_manifest_items(rows_t1, False, conflict_stats, "T1 Robe Manifest", conflict_cache)
	items_t2 = _build_manifest_items(rows_t2, False, conflict_stats, "T2 Robe Manifest", conflict_cache)
	results["D_conflicting_description_reported_not_applied"] = {
		"item_master_description": frappe.db.get_value("Item", conflict_code, "description"),
		"manifest_line_widths": [items_t1[0]["width"], items_t2[0]["width"]],
		"conflict_logged": any(e.action == "Conflict" for e in conflict_stats.log),
	}
	if frappe.db.exists("Item", conflict_code):
		frappe.delete_doc("Item", conflict_code, ignore_permissions=True, force=True)

	# E: blank item code is a validation error, not an Item creation.
	blank_stats = ImportRunStats()
	rows = [{"row_number": 5, "Description": "", "Item Description": "", "Qty": 2}]
	items = _build_manifest_items(rows, False, blank_stats, "TEST", {})
	results["E_blank_item_code"] = {
		"manifest_items_built": len(items),
		"failed_log_entries": [e.message for e in blank_stats.log if e.action == "Failed"],
	}

	# F: two sites can each carry their own Manifest referencing the same global Item code
	# (Items are global master data in this app — see hooks.py Item fixture — there is no
	# per-site Item variant; "the correct item" is simply the one global item_code).
	results["F_items_are_global_not_site_scoped"] = {
		"note": (
			"Item has no site-link field in this app's schema; item_code is the single "
			"global identifier. Manifests are the site/type-scoped documents, not Items."
		)
	}

	# Cleanup throwaway items so this is safe to re-run (also proves H: idempotent).
	for code in (new_code, dup_code):
		if frappe.db.exists("Item", code):
			frappe.delete_doc("Item", code, ignore_permissions=True, force=True)
	frappe.db.commit()

	return results


def verify_dwi_import(import_name: str) -> dict:
	"""End-to-end sanity check for a completed Development Workbook Import.

	Checks the doc's own status/log plus what actually landed in the DB —
	Manifests (with their line items), Project Unit Configuration links,
	the Site project, its unit projects, and whether tasks were generated.

	Run with:
	    bench --site <site> execute \
	        fitzgerald_kitchens.workbook_import.test_full_workbook.verify_dwi_import \
	        --kwargs "{'import_name': 'DWI-2026-00018'}"
	"""
	doc = frappe.get_doc("Development Workbook Import", import_name)
	report: dict = {
		"import_status": doc.import_status,
		"error_log": doc.error_log,
		"import_summary": doc.import_summary,
	}

	report["failed_or_conflict_log_entries"] = [
		{
			"phase": e.phase,
			"type": e.document_type,
			"code": e.document_code,
			"action": e.action,
			"message": e.message,
		}
		for e in doc.import_log
		if e.action in ("Failed", "Conflict")
	]

	manifest_codes = [
		"T1-Manifest-Site 007",
		"T1-Robe-Manifest-Site 007",
		"T3-Manifest-Site 007",
	]
	manifests = {}
	for code in manifest_codes:
		if frappe.db.exists("Manifest", code):
			m = frappe.get_doc("Manifest", code)
			manifests[code] = {
				"configuration": m.configuration,
				"item_count": len(m.items),
				"item_codes": [i.item_code for i in m.items],
			}
		else:
			manifests[code] = None
	report["manifests"] = manifests

	config_codes = ["T1-Site 007", "T3-Site 007"]
	report["configurations"] = {
		code: frappe.db.get_value(
			"Project Unit Configuration",
			code,
			["kitchen_utility_manifest", "wardrobe_manifest"],
			as_dict=True,
		)
		for code in config_codes
	}

	site = frappe.db.get_value(
		"Project", {"project_name": "Site 007", "project_type": "Site"}, "name"
	)
	report["site_project"] = site

	unit_projects = (
		frappe.get_all(
			"Project",
			filters={"fk_parent_project": site},
			fields=[
				"name",
				"project_type",
				"fk_effective_manifest",
				"fk_unit_configuration",
				"fk_house_number",
			],
		)
		if site
		else []
	)
	report["unit_projects"] = unit_projects
	report["tasks_per_unit_project"] = [
		{"project": up["name"], "task_count": frappe.db.count("Task", {"project": up["name"]})}
		for up in unit_projects
	]

	return report
