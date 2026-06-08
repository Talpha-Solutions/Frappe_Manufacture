# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.naming import NamingSeries
from frappe.utils import cint

from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE

SITE_NAMING_SERIES = "PROJ-.####"

# project_type -> naming series (document ID: UNIT-KIT-00001, etc.)
UNIT_NAMING_SERIES_BY_TYPE: dict[str, str] = {
	"Kitchen": "UNIT-KIT-.#####",
	"Robe": "UNIT-ROB-.#####",
	"Utility": "UNIT-UTL-.#####",
	"Vanity Unit": "UNIT-VAN-.#####",
	"Pantry": "UNIT-PAN-.#####",
	"Unit": "UNIT-UNT-.#####",
}

DEFAULT_UNIT_NAMING_SERIES = "UNIT-UNT-.#####"

ALL_PROJECT_NAMING_SERIES: tuple[str, ...] = (
	SITE_NAMING_SERIES,
	*UNIT_NAMING_SERIES_BY_TYPE.values(),
)


def get_naming_series_for_project_type(project_type: str | None) -> str:
	project_type = (project_type or "").strip()
	if project_type == SITE_PROJECT_TYPE:
		return SITE_NAMING_SERIES
	return UNIT_NAMING_SERIES_BY_TYPE.get(project_type, DEFAULT_UNIT_NAMING_SERIES)


def apply_project_naming_series(doc, method=None) -> None:
	"""before_insert: assign naming series from project_type for new projects only."""
	if not doc.is_new():
		return

	project_type = doc.get("project_type")
	if not project_type:
		return

	doc.naming_series = get_naming_series_for_project_type(project_type)


def ensure_project_naming_series_options() -> None:
	"""Register Site + unit naming series on ERPNext Project."""
	options = "\n".join(dict.fromkeys(ALL_PROJECT_NAMING_SERIES))
	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Project", "field_name": "naming_series", "property": "options"},
		"name",
	)

	if existing:
		frappe.db.set_value("Property Setter", existing, "value", options)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Project",
				"fieldname": "naming_series",
				"property": "options",
				"value": options,
				"property_type": "Text",
			}
		)

	frappe.clear_cache(doctype="Project")
	ensure_unit_series_counters()


def ensure_unit_series_counters() -> None:
	"""Align tabSeries counters so the next unit project ID is max(existing) + 1, never 00000."""
	for naming_series in UNIT_NAMING_SERIES_BY_TYPE.values():
		_sync_series_counter(naming_series)


def _sync_series_counter(naming_series: str) -> None:
	prefix = NamingSeries(naming_series).get_prefix()
	max_existing = _max_numeric_suffix("Project", prefix)
	current = _get_series_current(prefix)

	# getseries returns (current + 1); store the last issued number.
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
