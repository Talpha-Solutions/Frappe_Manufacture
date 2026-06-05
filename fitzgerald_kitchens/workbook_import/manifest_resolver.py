# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

from fitzgerald_kitchens.setup.project_unit_fields import KITCHEN_PROJECT_TYPE

KITCHEN_UTILITY_MANIFEST_TYPES = frozenset(
	{
		KITCHEN_PROJECT_TYPE,
		"Utility",
		"Vanity Unit",
		"Pantry",
	}
)
ROBE_MANIFEST_TYPE = "Robe"


def resolve_effective_manifest(config_code: str | None, project_type: str | None) -> str | None:
	"""Return the template manifest for a unit project from its PUC and project type."""
	config_code = (config_code or "").strip()
	project_type = (project_type or "").strip()
	if not config_code or not project_type:
		return None

	if not frappe.db.exists("Project Unit Configuration", config_code):
		return None

	puc = frappe.db.get_value(
		"Project Unit Configuration",
		config_code,
		["kitchen_utility_manifest", "wardrobe_manifest"],
		as_dict=True,
	)
	if not puc:
		return None

	if project_type == ROBE_MANIFEST_TYPE:
		return puc.wardrobe_manifest or None

	if project_type in KITCHEN_UTILITY_MANIFEST_TYPES:
		return puc.kitchen_utility_manifest or None

	return None
