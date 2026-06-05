# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

CABINET_KEYS = ("base_units", "wall_units", "tall_units", "drawer_packs")


class TenderConfiguration(Document):
	def validate(self):
		if not self.template:
			frappe.throw(_("Template is required."))

		rows = _parse_rows_json(self.config_rows_json)
		template_rows = _get_template_rows(self.template)
		rows_total = _validate_and_calculate_rows(rows, template_rows)
		cabinet_prices = _get_template_cabinet_prices(self.template)
		cabinet_total = _apply_cabinet_costing(self, cabinet_prices)
		self.cabinets_total = cabinet_total
		self.total_cost_per_kitchen = cabinet_total + rows_total
		self.grand_total_cost = self.total_cost_per_kitchen * flt(self.kitchens_to_tender or 0)
		_apply_tender_pricing(self)
		self.config_rows_json = json.dumps(rows)
		self.cabinet_prices_json = json.dumps(cabinet_prices)

	def get_print_summary(self) -> dict:
		"""Pre-computed values for custom Print Format (Jinja cannot parse JSON reliably)."""
		rows = []
		if self.config_rows_json:
			try:
				parsed = json.loads(self.config_rows_json)
				rows = parsed if isinstance(parsed, list) else []
			except Exception:
				rows = []
		cabinet_units_total = flt(self.cabinets_total)
		cabinets_builder_total = 0.0
		hardware_total = 0.0
		worktops_total = 0.0
		appliances_total = 0.0
		direct_labour_total = 0.0
		indirect_total = 0.0
		other_total = 0.0

		for row in rows:
			amount = flt(row.get("amount"))
			section = row.get("section") or ""
			item_group = (row.get("item_group") or "").strip()

			if item_group == "Hardware":
				hardware_total += amount
			elif section == "CABINETS":
				cabinets_builder_total += amount
			elif section == "WORKTOPS":
				worktops_total += amount
			elif section == "APPLIANCES":
				appliances_total += amount
			elif section == "DIRECT LABOUR":
				direct_labour_total += amount
			elif section == "INDIRECT & FIXED COSTS":
				indirect_total += amount
			else:
				other_total += amount

		# Cabinets line = unit pricing + CABINETS builder rows (excluding Hardware)
		cabinets_total = cabinet_units_total + cabinets_builder_total

		kitchens = flt(self.kitchens_to_tender or 0)
		total_material = cabinets_total + worktops_total + hardware_total + appliances_total
		total_labour_direct = direct_labour_total
		total_indirect = indirect_total
		display_total_per_kitchen = (
			cabinets_total
			+ worktops_total
			+ hardware_total
			+ appliances_total
			+ direct_labour_total
			+ indirect_total
			+ other_total
		)
		total_cost_per_kitchen = flt(self.total_cost_per_kitchen) or display_total_per_kitchen
		total_cost = total_material + total_labour_direct + total_indirect + other_total
		grand_total_cost = flt(self.grand_total_cost) or total_cost * kitchens
		cost_base = flt(self.cost_base) or grand_total_cost
		margin_pct = flt(self.target_margin_pct)
		margin_amount = flt(self.margin_amount) or cost_base * (margin_pct / 100.0)
		tender_price_total = flt(self.tender_price_total) or cost_base + margin_amount
		tender_price_per_kitchen = (
			flt(self.tender_price_per_kitchen) or (tender_price_total / kitchens if kitchens else 0)
		)

		return {
			"tender_name": self.tender_name,
			"kitchens": kitchens,
			"cabinets_total": cabinets_total,
			"worktops_total": worktops_total,
			"hardware_total": hardware_total,
			"appliances_total": appliances_total,
			"direct_labour_total": direct_labour_total,
			"indirect_total": indirect_total,
			"total_cost_per_kitchen": total_cost_per_kitchen,
			"other_total": other_total,
			"total_material": total_material,
			"total_labour_direct": total_labour_direct,
			"total_indirect": total_indirect,
			"total_cost": total_cost,
			"total_material_tender": total_material * kitchens,
			"total_labour_tender": total_labour_direct * kitchens,
			"total_indirect_tender": total_indirect * kitchens,
			"grand_total_cost": grand_total_cost,
			"target_margin_pct": margin_pct,
			"cost_base": cost_base,
			"margin_amount": margin_amount,
			"tender_price_total": tender_price_total,
			"tender_price_per_kitchen": tender_price_per_kitchen,
		}


def _parse_rows_json(config_rows_json: str) -> list[dict]:
	if not config_rows_json:
		return []
	try:
		rows = json.loads(config_rows_json)
	except Exception:
		frappe.throw(_("Configuration rows data is invalid JSON."))
	if not isinstance(rows, list):
		frappe.throw(_("Configuration rows data is invalid."))
	return rows


def _validate_and_calculate_rows(rows: list[dict], template_rows: list[dict]) -> float:
	template_keys = {(r["section"], r["label"]) for r in template_rows}
	provided_keys = {(r.get("section"), r.get("label")) for r in rows}
	if template_keys != provided_keys:
		frappe.throw(_("Configuration rows must match the selected template rows."))

	total = 0.0
	for row in rows:
		row["qty"] = flt(row.get("qty"))
		if row["qty"] < 0:
			frappe.throw(_("Qty cannot be negative for row {0}.").format(row.get("label")))

		if not row.get("price_row"):
			row["item_code"] = ""
			row["rate"] = 0
			row["amount"] = 0
			continue

		item_price = frappe.db.get_value(
			"Item Price",
			row["price_row"],
			["name", "item_code", "price_list_rate", "currency", "uom"],
			as_dict=True,
		)
		if not item_price:
			frappe.throw(_("Invalid price selection for row {0}.").format(row.get("label")))

		actual_group = frappe.db.get_value("Item", item_price.item_code, "item_group")
		if row.get("item_group") and actual_group != row.get("item_group"):
			frappe.throw(
				_("Selected item does not belong to Item Group {0} for row {1}.").format(
					row.get("item_group"), row.get("label")
				)
			)

		row["item_code"] = item_price.item_code
		row["rate"] = flt(item_price.price_list_rate)
		row["currency"] = item_price.currency
		row["uom"] = item_price.uom
		row["amount"] = flt(row["qty"]) * flt(row["rate"])
		total += flt(row["amount"])

	return total


def _apply_cabinet_costing(doc: TenderConfiguration, cabinet_prices: dict) -> float:
	cabinet_total = 0.0
	for key in CABINET_KEYS:
		price_data = cabinet_prices.get(key) or {}
		rate = flt(price_data.get("rate"))
		qty = flt(getattr(doc, key, 0))
		amount = qty * rate
		setattr(doc, f"{key}_rate", rate)
		setattr(doc, f"{key}_amount", amount)
		cabinet_total += amount
	return cabinet_total


def _apply_tender_pricing(doc: TenderConfiguration):
	doc.cost_base = flt(doc.grand_total_cost)
	doc.target_margin_pct = flt(doc.target_margin_pct)
	doc.margin_amount = flt(doc.cost_base) * (flt(doc.target_margin_pct) / 100.0)
	doc.tender_price_total = flt(doc.cost_base) + flt(doc.margin_amount)
	kitchens = flt(doc.kitchens_to_tender or 0)
	doc.tender_price_per_kitchen = flt(doc.tender_price_total) / kitchens if kitchens else 0


def _get_template_cabinet_prices(template: str) -> dict:
	template_doc = frappe.get_doc("Kitchen Configuration Template", template)
	mapping = {
		"base_units": template_doc.base_units_price_row,
		"wall_units": template_doc.wall_units_price_row,
		"tall_units": template_doc.tall_units_price_row,
		"drawer_packs": template_doc.drawer_packs_price_row,
	}
	cabinet_prices = {}
	for key, price_row in mapping.items():
		if not price_row:
			frappe.throw(_("Cabinet price mapping is missing for {0}.").format(key.replace("_", " ").title()))
		item_price = frappe.db.get_value(
			"Item Price",
			price_row,
			["name", "item_code", "price_list_rate", "currency", "uom"],
			as_dict=True,
		)
		if not item_price:
			frappe.throw(_("Invalid template cabinet price row for {0}.").format(key.replace("_", " ").title()))
		cabinet_prices[key] = {
			"price_row": item_price.name,
			"item_code": item_price.item_code,
			"rate": flt(item_price.price_list_rate),
			"currency": item_price.currency,
			"uom": item_price.uom,
		}
	return cabinet_prices


@frappe.whitelist()
def get_default_template():
	return frappe.db.get_value(
		"Kitchen Configuration Template",
		{"is_default": 1},
		"name",
	)


@frappe.whitelist()
def get_template_rows(template: str):
	if not template:
		return []
	return _get_template_rows(template)


@frappe.whitelist()
def get_template_cabinet_prices(template: str):
	if not template:
		return {}
	return _get_template_cabinet_prices(template)


def _get_template_rows(template: str) -> list[dict]:
	rows = frappe.get_all(
		"Kitchen Configuration Template Row",
		filters={"parent": template},
		fields=[
			"section",
			"tag",
			"label",
			"subtitle",
			"item_group",
			"qty_label",
			"default_qty",
		],
		order_by="idx asc",
	)
	for row in rows:
		row["qty"] = flt(row.get("default_qty") or 1)
	return rows


@frappe.whitelist()
def get_price_options(item_group: str):
	if not item_group:
		return []

	rows = frappe.db.sql(
		"""
		select
			ip.name as price_row,
			i.name as item_code,
			i.item_name,
			ip.price_list,
			ip.price_list_rate as rate,
			ip.currency,
			ip.uom
		from `tabItem Price` ip
		inner join `tabItem` i on i.name = ip.item_code
		where i.disabled = 0
		  and i.item_group = %s
		order by i.item_name asc, ip.price_list asc, ip.uom asc
		""",
		(item_group,),
		as_dict=True,
	)
	return rows
