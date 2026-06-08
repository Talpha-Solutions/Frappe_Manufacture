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
