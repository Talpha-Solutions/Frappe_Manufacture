# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

LABEL_CATEGORY_ASSEMBLY = "Assembly"
LABEL_CATEGORY_FITTING = "Fitting Kit"
LABEL_CATEGORY_EXTRA = "Extra"

LABEL_CATEGORY_OPTIONS = (
	LABEL_CATEGORY_ASSEMBLY,
	LABEL_CATEGORY_FITTING,
	LABEL_CATEGORY_EXTRA,
)


def resolve_manifest_linked_bom(item_code: str) -> str | None:
	"""Default manifest BOM link from Item.default_bom."""
	if not item_code:
		return None
	return frappe.db.get_value("Item", item_code, "default_bom") or None


def resolve_label_category(item_code: str, linked_bom: str | None = None) -> str:
	"""Assembly when a BOM is linked; otherwise Fitting Kit."""
	bom = (linked_bom or "").strip() or resolve_manifest_linked_bom(item_code) or ""
	if bom:
		return LABEL_CATEGORY_ASSEMBLY
	return LABEL_CATEGORY_FITTING


def sync_manifest_line_labels(line) -> None:
	"""Apply linked BOM default and read-only label category on a manifest item row."""
	if not line.item_code:
		return
	if not line.linked_bom:
		line.linked_bom = resolve_manifest_linked_bom(line.item_code)
	line.label_category = resolve_label_category(line.item_code, line.linked_bom)


def refresh_all_manifest_label_categories() -> int:
	updated = 0
	for row in frappe.db.sql(
		"""
		SELECT name, item_code, linked_bom, label_category
		FROM `tabManifest Item`
		WHERE item_code IS NOT NULL AND item_code != ''
		""",
		as_dict=True,
	):
		linked_bom = (row.linked_bom or "").strip() or resolve_manifest_linked_bom(row.item_code)
		label_category = resolve_label_category(row.item_code, linked_bom)
		if row.label_category != label_category or row.linked_bom != linked_bom:
			frappe.db.set_value(
				"Manifest Item",
				row.name,
				{
					"linked_bom": linked_bom,
					"label_category": label_category,
				},
				update_modified=False,
			)
			updated += 1

	if updated:
		frappe.db.commit()
	return updated
