# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.naming import NamingSeries, make_autoname
from frappe.utils import cint

TENDER_NAMING_SERIES = "KC-.YYYY.-.#####"
LITERAL_BAD_NAME = "KC-.YYYY.-.#####"


def execute():
	_fix_literal_bad_name()
	_backfill_missing_naming_series()
	_sync_tender_series_counter()
	frappe.clear_cache(doctype="Tender Configuration")


def _fix_literal_bad_name() -> None:
	if not frappe.db.exists("Tender Configuration", LITERAL_BAD_NAME):
		return

	if not frappe.db.has_column("Tender Configuration", "naming_series"):
		return

	frappe.db.set_value(
		"Tender Configuration",
		LITERAL_BAD_NAME,
		"naming_series",
		TENDER_NAMING_SERIES,
		update_modified=False,
	)

	doc = frappe.get_doc("Tender Configuration", LITERAL_BAD_NAME)
	new_name = make_autoname(TENDER_NAMING_SERIES, doc=doc)
	if new_name and new_name != LITERAL_BAD_NAME:
		frappe.rename_doc("Tender Configuration", LITERAL_BAD_NAME, new_name, force=True)


def _backfill_missing_naming_series() -> None:
	if not frappe.db.has_column("Tender Configuration", "naming_series"):
		return

	frappe.db.sql(
		"""
		update `tabTender Configuration`
		set naming_series = %s
		where ifnull(naming_series, '') = ''
		""",
		TENDER_NAMING_SERIES,
	)


def _sync_tender_series_counter() -> None:
	prefix = NamingSeries(TENDER_NAMING_SERIES).get_prefix()
	max_existing = _max_numeric_suffix("Tender Configuration", prefix)
	current = _get_series_current(prefix)
	target = max(max_existing, current, 0)

	if current < 0 or current != target:
		if _series_exists(prefix):
			frappe.db.sql("UPDATE `tabSeries` SET `current` = %s WHERE `name` = %s", (target, prefix))
		else:
			frappe.db.sql(
				"INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)",
				(prefix, target),
			)


def _series_exists(prefix: str) -> bool:
	return bool(
		frappe.db.sql("SELECT 1 FROM `tabSeries` WHERE `name` = %s LIMIT 1", (prefix,))
	)


def _get_series_current(prefix: str) -> int:
	row = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,))
	return cint(row[0][0]) if row else 0


def _max_numeric_suffix(doctype: str, prefix: str) -> int:
	names = frappe.db.get_all(
		doctype,
		filters={"name": ["like", f"{prefix}%"]},
		pluck="name",
	)
	max_no = 0
	for name in names:
		suffix = name[len(prefix) :]
		if suffix.isdigit():
			max_no = max(max_no, cint(suffix))
	return max_no
