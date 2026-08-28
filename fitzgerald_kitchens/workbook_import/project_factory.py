# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import frappe
from frappe.utils import cint

from fitzgerald_kitchens.setup.project_manifest_amend import project_has_unit_snapshot_manifest
from fitzgerald_kitchens.setup.project_naming import get_naming_series_for_project_type
from fitzgerald_kitchens.setup.project_unit_fields import KITCHEN_PROJECT_TYPE, SITE_PROJECT_TYPE
from fitzgerald_kitchens.workbook_import.constants import (
	SUB_UNIT_PROJECT_QTY_COLUMNS,
	kitchen_qty,
)
from fitzgerald_kitchens.workbook_import.import_log import ImportRunStats, WorkbookImportLogEntry
from fitzgerald_kitchens.workbook_import.manifest_resolver import resolve_effective_manifest
from fitzgerald_kitchens.workbook_import.naming import build_unit_project_name
from fitzgerald_kitchens.workbook_import.qty_rows import parse_row_qtys


@dataclass
class ImportLogEntry:
	"""Legacy adapter for quantity-only import path."""

	row_number: int
	developer: str
	site_name: str
	house_number: str
	project_type: str
	action: str
	project: str | None = None
	message: str | None = None


@dataclass
class ImportStats:
	sites_created: int = 0
	sites_updated: int = 0
	units_created: int = 0
	units_updated: int = 0
	configurations_linked: int = 0
	tasks_from_template_applied: int = 0
	log: list[ImportLogEntry] = field(default_factory=list)


class WorkbookProjectFactory:
	def __init__(
		self,
		*,
		company: str,
		create_missing_developer: bool = False,
		generate_tasks_from_template: bool = False,
		project_template: str = "",
		run_stats: ImportRunStats | None = None,
	):
		self.company = company
		self.create_missing_developer = create_missing_developer
		self.generate_tasks_from_template = bool(generate_tasks_from_template)
		self.project_template = (project_template or "").strip()
		self.stats = ImportStats()
		self._run_stats = run_stats
		self._site_cache: dict[str, str] = {}
		self._kitchen_cache: dict[tuple[str, str], str | None] = {}

	def import_rows(self, rows: list[dict[str, Any]]) -> ImportStats:
		for row in rows:
			self._import_row(row)
		return self.stats

	def _import_row(self, row: dict[str, Any]) -> None:
		developer = row["developer"]
		site_name = row["site_name"]
		house_number = str(row["house_number"]).strip()
		config_code = row["configuration_code"]
		bedrooms = cint(row.get("bedrooms") or 0)
		qtys = parse_row_qtys(row)
		row_number = cint(row.get("row_number"))

		customer = self._resolve_developer(developer)
		site = self._ensure_site(developer, site_name, customer, row_number)
		kitchen_project = None

		kitchen_qty_value = kitchen_qty(qtys)
		if kitchen_qty_value > 0:
			kitchen_project = self._upsert_unit_project(
				row_number=row_number,
				developer=developer,
				customer=customer,
				site_name=site_name,
				site=site,
				house_number=house_number,
				project_type=KITCHEN_PROJECT_TYPE,
				qty=kitchen_qty_value,
				bedrooms=bedrooms,
				config_code=config_code,
				parent_unit=None,
			)
			self._kitchen_cache[(site, house_number)] = kitchen_project

		for qty_col, project_type in SUB_UNIT_PROJECT_QTY_COLUMNS:
			qty = qtys.get(qty_col, 0)
			if qty <= 0:
				continue

			if not kitchen_project:
				kitchen_project = self._find_kitchen_project(site, house_number)

			if not kitchen_project:
				self._log_failure(
					row_number,
					developer,
					site_name,
					house_number,
					project_type,
					"Kitchen project is required before creating sub-units.",
				)
				continue

			self._upsert_unit_project(
				row_number=row_number,
				developer=developer,
				customer=customer,
				site_name=site_name,
				site=site,
				house_number=house_number,
				project_type=project_type,
				qty=qty,
				bedrooms=bedrooms,
				config_code=config_code,
				parent_unit=kitchen_project,
			)

	def _project_template_fields(self, project_type: str) -> dict[str, str]:
		"""Template applies to unit projects only; Site is a parent container."""
		if project_type == SITE_PROJECT_TYPE:
			return {}
		if self.generate_tasks_from_template and self.project_template:
			return {"project_template": self.project_template}
		return {}

	def _maybe_apply_project_template(self, project_name: str, project_type: str) -> bool:
		"""Apply template tasks to a unit project that has no tasks yet (e.g. on re-import).

		ERPNext marks project_template (From Template) as set_only_once, so it cannot be
		assigned on doc.save() for existing projects. Set via db.set_value first, then
		save so validate() runs copy_from_template() without changing that field.
		"""
		template_fields = self._project_template_fields(project_type)
		if not template_fields:
			return False
		if frappe.db.get_all("Task", {"project": project_name}, limit=1):
			return False

		template_name = template_fields["project_template"]
		current_template = frappe.db.get_value("Project", project_name, "project_template")
		if current_template and current_template != template_name:
			return False

		if not current_template:
			frappe.db.set_value(
				"Project",
				project_name,
				"project_template",
				template_name,
				update_modified=False,
			)

		doc = frappe.get_doc("Project", project_name)
		doc.save(ignore_permissions=True)
		self.stats.tasks_from_template_applied += 1
		if self._run_stats:
			self._run_stats.tasks_from_template_applied += 1
		return True

	def _site_project_name(self, site_name: str) -> str:
		return site_name.strip()

	def _unit_project_name(self, site_name: str, house_number: str, project_type: str) -> str:
		return build_unit_project_name(site_name, house_number, project_type)

	def _ensure_site(
		self, developer: str, site_name: str, customer: str, row_number: int
	) -> str:
		site_project_name = self._site_project_name(site_name)
		if site_project_name in self._site_cache:
			return self._site_cache[site_project_name]

		existing = frappe.db.get_value(
			"Project",
			{"project_type": SITE_PROJECT_TYPE, "project_name": site_project_name},
			"name",
		)
		if existing:
			self._apply_developer(existing, customer)
			self._site_cache[site_project_name] = existing
			self.stats.sites_updated += 1
			if self._run_stats:
				self._run_stats.sites_updated += 1
			self._append_log(
				phase="Phase 3",
				document_type="Project",
				document_code=site_project_name,
				action="Updated",
				row_number=row_number,
				developer=developer,
				site_name=site_name,
				project_type=SITE_PROJECT_TYPE,
				project=existing,
				message="Site exists — developer synced.",
			)
			return existing

		doc = frappe.get_doc(
			{
				"doctype": "Project",
				"naming_series": get_naming_series_for_project_type(SITE_PROJECT_TYPE),
				"project_name": site_project_name,
				"project_type": SITE_PROJECT_TYPE,
				"company": self.company,
				"status": "Open",
				**self._developer_field_values(customer),
			}
		)
		doc.insert(ignore_permissions=True)
		self._site_cache[site_project_name] = doc.name
		self.stats.sites_created += 1
		if self._run_stats:
			self._run_stats.sites_created += 1
		self._append_log(
			phase="Phase 3",
			document_type="Project",
			document_code=site_project_name,
			action="Created",
			row_number=row_number,
			developer=developer,
			site_name=site_name,
			project_type=SITE_PROJECT_TYPE,
			project=doc.name,
		)
		return doc.name

	def _upsert_unit_project(
		self,
		*,
		row_number: int,
		developer: str,
		customer: str,
		site_name: str,
		site: str,
		house_number: str,
		project_type: str,
		qty: int,
		bedrooms: int,
		config_code: str,
		parent_unit: str | None,
	) -> str:
		project_name = self._unit_project_name(site_name, house_number, project_type)
		existing = frappe.db.get_value(
			"Project",
			{
				"fk_parent_project": site,
				"fk_house_number": house_number,
				"project_type": project_type,
			},
			"name",
		)

		values = {
			"naming_series": get_naming_series_for_project_type(project_type),
			"project_name": project_name,
			"project_type": project_type,
			"fk_parent_project": site,
			"fk_house_number": house_number,
			"fk_bedrooms": bedrooms or None,
			"fk_unit_qty": qty,
			"company": self.company,
			"status": "Open",
			"fk_parent_unit_project": parent_unit,
			**self._developer_field_values(customer),
			"fk_unit_configuration": config_code,
		}

		effective_manifest = resolve_effective_manifest(config_code, project_type)
		if effective_manifest and not (
			existing and project_has_unit_snapshot_manifest(existing)
		):
			values["fk_effective_manifest"] = effective_manifest

		if existing:
			frappe.db.set_value("Project", existing, values, update_modified=True)
			self.stats.units_updated += 1
			self.stats.configurations_linked += 1
			if self._run_stats:
				self._run_stats.units_updated += 1
				self._run_stats.configurations_linked += 1
			if self._maybe_apply_project_template(existing, project_type):
				self._append_log(
					phase="Phase 3",
					document_type="Project",
					document_code=project_name,
					action="Updated",
					row_number=row_number,
					developer=developer,
					site_name=site_name,
					house_number=house_number,
					project_type=project_type,
					project=existing,
					message="Tasks generated from template.",
				)
			else:
				self._append_log(
					phase="Phase 3",
					document_type="Project",
					document_code=project_name,
					action="Updated",
					row_number=row_number,
					developer=developer,
					site_name=site_name,
					house_number=house_number,
					project_type=project_type,
					project=existing,
				)
			return existing

		doc = frappe.get_doc(
			{"doctype": "Project", **values, **self._project_template_fields(project_type)}
		)
		doc.insert(ignore_permissions=True)
		if self.generate_tasks_from_template and self.project_template and project_type != SITE_PROJECT_TYPE:
			self.stats.tasks_from_template_applied += 1
			if self._run_stats:
				self._run_stats.tasks_from_template_applied += 1
		self.stats.units_created += 1
		self.stats.configurations_linked += 1
		if self._run_stats:
			self._run_stats.units_created += 1
			self._run_stats.configurations_linked += 1
		self._append_log(
			phase="Phase 3",
			document_type="Project",
			document_code=project_name,
			action="Created",
			row_number=row_number,
			developer=developer,
			site_name=site_name,
			house_number=house_number,
			project_type=project_type,
			project=doc.name,
		)
		return doc.name

	def _find_kitchen_project(self, site: str, house_number: str) -> str | None:
		cache_key = (site, house_number)
		if cache_key in self._kitchen_cache:
			return self._kitchen_cache[cache_key]

		name = frappe.db.get_value(
			"Project",
			{
				"fk_parent_project": site,
				"fk_house_number": house_number,
				"project_type": KITCHEN_PROJECT_TYPE,
			},
			"name",
		)
		self._kitchen_cache[cache_key] = name
		return name

	def _developer_field_values(self, customer: str) -> dict[str, str]:
		return {"fk_developer": customer, "customer": customer}

	def _apply_developer(self, project: str, customer: str) -> None:
		current = frappe.db.get_value(
			"Project", project, ["fk_developer", "customer"], as_dict=True
		)
		if not current:
			return

		updates = {}
		if current.get("fk_developer") != customer:
			updates["fk_developer"] = customer
		if current.get("customer") != customer:
			updates["customer"] = customer

		if updates:
			frappe.db.set_value("Project", project, updates, update_modified=True)

	def _resolve_developer(self, developer: str) -> str:
		developer = (developer or "").strip()
		if frappe.db.exists("Customer", developer):
			return developer

		by_name = frappe.db.get_value("Customer", {"customer_name": developer}, "name")
		if by_name:
			return by_name

		if not self.create_missing_developer:
			frappe.throw(frappe._("Customer '{0}' not found.").format(developer))

		from frappe.defaults import get_global_default

		customer_group = get_global_default("customer_group")
		territory = get_global_default("territory")
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": developer,
				"customer_type": "Company",
				"customer_group": customer_group,
				"territory": territory,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _append_log(self, **kwargs) -> None:
		if self._run_stats:
			self._run_stats.log.append(WorkbookImportLogEntry(**kwargs))
			return
		self.stats.log.append(
			ImportLogEntry(
				row_number=kwargs.get("row_number", 0),
				developer=kwargs.get("developer", ""),
				site_name=kwargs.get("site_name", ""),
				house_number=kwargs.get("house_number", ""),
				project_type=kwargs.get("project_type", ""),
				action=kwargs.get("action", ""),
				project=kwargs.get("project"),
				message=kwargs.get("message"),
			)
		)

	def _log_failure(
		self,
		row_number: int,
		developer: str,
		site_name: str,
		house_number: str,
		project_type: str,
		message: str,
	) -> None:
		self._append_log(
			phase="Phase 3",
			document_type="Project",
			document_code="",
			action="Failed",
			row_number=row_number,
			developer=developer,
			site_name=site_name,
			house_number=house_number,
			project_type=project_type,
			message=message,
		)


def build_project_name(site_name: str, house_number: str, project_type: str) -> str:
	"""Human-readable unit project title from Quantity Sheet Name column."""
	return build_unit_project_name(site_name, house_number, project_type)
