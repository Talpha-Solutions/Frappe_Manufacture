import json

import frappe

from fitzgerald_kitchens.fitzgerald_kitchens.doctype.pre_production_plan.pre_production_plan import update_tender_totals



def execute():
	"""Re-cost manifest rows whose cost source doesn't suit their item.

	Manufactured items (Default Material Request Type "Manufacture") are costed from a BOM and
	bought-in items from a price or their last purchase rate. Rows saved before that, e.g. a
	manufactured cabinet still on its Standard Selling price, move to the item's default source
	(its default BOM, or not costed if it has none); the manifest's totals and its plan's totals are
	worked out again. Only manifests with such a row are touched, so no other stored total changes.

	Safe to run again, e.g. after items are switched to Manufacture in bulk:
	bench --site <site> execute fitzgerald_kitchens.patches.v1_0.match_cost_sources_to_item_type.execute
	"""
	plans = set()
	for name in frappe.get_all("Pre Production Manifest", pluck="name"):
		doc = frappe.get_doc("Pre Production Manifest", name)
		before = _sources(doc.config_rows_json)
		old_total = doc.total_cost_per_kitchen
		try:
			doc.calculate_costs()
		except Exception as e:
			print(f"{name}: skipped ({frappe.utils.strip_html(str(e))[:120]})")
			continue
		if _sources(doc.config_rows_json) == before:
			continue
		doc.db_update()
		plans.add(doc.pre_production_plan)
		print(f"{name}: cost sources updated, total per unit {old_total} -> {doc.total_cost_per_kitchen}")
	for plan in plans - {None, ""}:
		update_tender_totals(plan)


def _sources(config_rows_json: str) -> list:
	"""Each row's (BOM, Item Price, source); rows saved before cost sources have only a price."""
	sources = []
	for row in json.loads(config_rows_json or "[]"):
		bom, price_row = row.get("bom") or "", row.get("price_row") or ""
		cost_from = row.get("cost_from") or ("BOM" if bom else "Price List" if price_row else "")
		sources.append((bom, price_row, cost_from if row.get("item_code") else ""))
	return sources
