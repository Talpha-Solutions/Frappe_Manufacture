# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

from fitzgerald_kitchens.setup.project_bom_fields import PROJECT_BOM_FIELDS, ensure_project_bom_fields


def execute():
	ensure_project_bom_fields()
	_migrate_bom_data_from_development_units()


def _migrate_bom_data_from_development_units() -> None:
	"""Copy BOM tab values from Development Units onto their linked Project."""
	if not frappe.db.has_column("Development Unit", "kitchen_required"):
		return

	project_names = frappe.get_all(
		"Development Unit",
		filters={"project": ["is", "set"]},
		pluck="project",
		distinct=True,
	)
	if not project_names:
		return

	select_fields = ["name", "project", *PROJECT_BOM_FIELDS]
	units = frappe.get_all(
		"Development Unit",
		filters={"project": ["in", project_names]},
		fields=select_fields,
		order_by="modified desc",
	)

	units_by_project: dict[str, list] = {}
	for unit in units:
		units_by_project.setdefault(unit.project, []).append(unit)

	for project_name in project_names:
		project_units = units_by_project.get(project_name) or []
		if not project_units:
			continue

		if _project_has_bom_data(project_name):
			continue

		source = _pick_source_unit(project_units)
		if not source:
			continue

		values = {field: source.get(field) for field in PROJECT_BOM_FIELDS}
		frappe.db.set_value("Project", project_name, values, update_modified=False)


def _project_has_bom_data(project_name: str) -> bool:
	existing = frappe.db.get_value("Project", project_name, PROJECT_BOM_FIELDS, as_dict=True)
	if not existing:
		return False
	return any(existing.get(field) not in (None, "", 0) for field in PROJECT_BOM_FIELDS)


def _pick_source_unit(units: list) -> dict | None:
	"""Prefer a unit that has BOM data; otherwise use the most recently modified."""
	for unit in units:
		if any(unit.get(field) for field in PROJECT_BOM_FIELDS):
			return unit
	return units[0] if units else None
