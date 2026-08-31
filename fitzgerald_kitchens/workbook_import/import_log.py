# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkbookImportLogEntry:
	phase: str
	document_type: str
	document_code: str
	action: str
	row_number: int = 0
	developer: str = ""
	site_name: str = ""
	house_number: str = ""
	project_type: str = ""
	project: str | None = None
	message: str | None = None


@dataclass
class ImportRunStats:
	manifests_created: int = 0
	manifests_updated: int = 0
	configurations_created: int = 0
	configurations_updated: int = 0
	sites_created: int = 0
	sites_updated: int = 0
	units_created: int = 0
	units_updated: int = 0
	configurations_linked: int = 0
	tasks_from_template_applied: int = 0
	items_created: int = 0
	items_updated: int = 0
	items_skipped: int = 0
	items_errors: int = 0
	log: list[WorkbookImportLogEntry] = field(default_factory=list)
