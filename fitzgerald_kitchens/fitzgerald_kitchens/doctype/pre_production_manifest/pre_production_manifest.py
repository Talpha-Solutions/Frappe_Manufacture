# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, fmt_money

from fitzgerald_kitchens.fitzgerald_kitchens.doctype.pre_production_plan.pre_production_plan import update_tender_totals
from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE
from fitzgerald_kitchens.fitzgerald_kitchens.doctype.pre_production_manifest_template.pre_production_manifest_template import (
	tender_party,
	validate_template_party,
)

# template row details a tender row always follows (its item, qty, costing, etc. are its own)
TEMPLATE_ROW_FIELDS = ("tag", "subtitle", "item_group", "qty_label")

# where a row's rate comes from: a manufactured item (Default Material Request Type "Manufacture")
# costs what one of its BOMs costs; any other item is bought in and costs a price from any price list,
# or its last purchase rate
MANUFACTURE_REQUEST_TYPE = "Manufacture"
COST_FROM_BOM = "BOM"
COST_FROM_PRICE_LIST = "Price List"
COST_FROM_LAST_PURCHASE = "Last Purchase Rate"


# while a tender is with the client, or closed, its manifests are fixed; Revise (or Reopen) the tender
# to change them. A won tender stays open, e.g. to add a variation before creating its units.
LOCKED_TENDER_STATUSES = ("Submitted", "Lost", "Cancelled")


class PreProductionManifest(Document):
	def before_insert(self):
		if not self.naming_series:
			self.naming_series = "KC-.YYYY.-.#####"

	def validate(self):
		self._check_tender_lock()
		if self.project_type == SITE_PROJECT_TYPE:
			frappe.throw(_("A tender manifest prices a unit's room, so its Project Type can't be Site."))
		if not self.template:
			frappe.throw(_("Template is required."))
		validate_template_party(self.template, *tender_party(self.pre_production_plan))
		self.calculate_costs()

	def calculate_costs(self):
		"""Cost every row and charge, and work out the totals and tender price."""
		rows = _parse_rows_json(self.config_rows_json)
		template_rows = _get_template_rows(self.template)
		rows_total = _validate_and_calculate_rows(rows, template_rows)
		other_costs = _parse_rows_json(self.other_costs_json)
		self.other_costs_total = _validate_and_calculate_other_costs(other_costs)
		self.other_costs_json = json.dumps(other_costs)
		self.total_cost_per_kitchen = rows_total + self.other_costs_total
		self.grand_total_cost = self.total_cost_per_kitchen * flt(self.kitchens_to_tender or 0)
		_apply_tender_pricing(self)
		self.config_rows_json = json.dumps(rows)

	def on_update(self):
		# keep the tender's totals in step; if the manifest moved, the old tender loses it
		previous = self.get_doc_before_save()
		update_tender_totals(self.pre_production_plan)
		if previous and previous.pre_production_plan and previous.pre_production_plan != self.pre_production_plan:
			update_tender_totals(previous.pre_production_plan)

	def on_trash(self):
		self._check_tender_lock()

	def after_delete(self):
		update_tender_totals(self.pre_production_plan)

	def _check_tender_lock(self):
		previous = None if self.is_new() else frappe.db.get_value("Pre Production Manifest", self.name, "pre_production_plan")
		for tender in {self.pre_production_plan, previous} - {None, ""}:
			status = frappe.db.get_value("Pre Production Plan", tender, "status")
			if status in LOCKED_TENDER_STATUSES:
				frappe.throw(
					_("Tender {0} is {1}, so its manifests can't be changed. Revise the tender to change them.").format(
						frappe.bold(tender), _(status)
					),
					title=_("Tender Locked"),
				)

	def get_print_summary(self) -> dict:
		"""Pre-computed values for custom Print Format (Jinja cannot parse JSON reliably)."""
		rows = []
		if self.config_rows_json:
			try:
				parsed = json.loads(self.config_rows_json)
				rows = parsed if isinstance(parsed, list) else []
			except Exception:
				rows = []
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

		# charges from the Other Costs section (per unit)
		other_total += flt(self.other_costs_total)

		# Cabinets line = the CABINETS builder rows (excluding Hardware)
		cabinets_total = cabinets_builder_total

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

	# row details come from the current template, never from the browser or an old copy on the
	# tender, so editing a template row (e.g. its item group) applies to tenders already using it
	template_by_key = {(r["section"], r["label"]): r for r in template_rows}

	total = 0.0
	for row in rows:
		template_row = template_by_key[(row.get("section"), row.get("label"))]
		for field in TEMPLATE_ROW_FIELDS:
			row[field] = template_row.get(field)
		row["remark"] = cstr(row.get("remark")).strip()
		row["qty"] = flt(row.get("qty"))
		if row["qty"] < 0:
			frappe.throw(_("Qty cannot be negative for row {0}.").format(row.get("label")))

		_apply_costing(row)
		total += flt(row["amount"])

	return total


def _apply_costing(row: dict):
	"""Check the row's item and where its cost comes from, and set its rate and amount.

	The row is costed by what it has chosen: a BOM (its unit cost), else an Item Price (any price
	list), else the item's Last Purchase Rate. The choice has to suit the item: a manufactured item
	(Default Material Request Type "Manufacture") is costed from a BOM and a bought-in item isn't, so
	a row whose item has changed type is moved to the item's default source first (see
	_match_cost_source).
	"""
	item_code = row.get("item_code") or ""
	if not item_code:
		row.update(item_code="", cost_from="", bom="", price_row="", price_list="", uom="", currency="")
		_apply_rate(row, 0)
		return

	item = frappe.db.get_value(
		"Item", item_code, ["item_group", "stock_uom", "last_purchase_rate", "default_material_request_type"], as_dict=True
	)
	if not item:
		frappe.throw(_("Item {0} not found for row {1}.").format(item_code, row.get("label")))
	if row.get("item_group") and item.item_group != row.get("item_group"):
		frappe.throw(
			_("Selected item does not belong to Item Group {0} for row {1}.").format(
				row.get("item_group"), row.get("label")
			)
		)

	_match_cost_source(row, item_code, item)

	# rows saved before costing sources had a Standard Selling price only
	cost_from = row.get("cost_from") or (COST_FROM_PRICE_LIST if row.get("price_row") else "")
	if row.get("bom"):
		cost_from = COST_FROM_BOM
	row.update(cost_from=cost_from, uom=item.stock_uom, currency=_default_currency())

	if cost_from == COST_FROM_BOM and row.get("bom"):
		bom = frappe.db.get_value(
			"BOM", row["bom"], ["item", "docstatus", "is_active", "total_cost", "quantity", "currency"], as_dict=True
		)
		if not bom or bom.docstatus != 1 or not bom.is_active:
			frappe.throw(_("BOM {0} for row {1} isn't a submitted, active BOM.").format(frappe.bold(row["bom"]), row.get("label")))
		if bom.item != item_code:
			frappe.throw(
				_("BOM {0} is for {1}, not {2} (row {3}).").format(frappe.bold(row["bom"]), bom.item, item_code, row.get("label"))
			)
		row.update(price_row="", price_list="", currency=bom.currency or row["currency"])
		_apply_rate(row, _bom_unit_cost(bom))
		return

	row["bom"] = ""
	if cost_from == COST_FROM_PRICE_LIST and row.get("price_row"):
		price = frappe.db.get_value(
			"Item Price", row["price_row"], ["item_code", "price_list", "price_list_rate", "currency", "uom"], as_dict=True
		)
		if not price or price.item_code != item_code:
			frappe.throw(_("Invalid price selection for row {0}.").format(row.get("label")))
		row.update(price_list=price.price_list, uom=price.uom or item.stock_uom, currency=price.currency)
		_apply_rate(row, price.price_list_rate)
		return

	row.update(price_row="", price_list="")
	if cost_from == COST_FROM_LAST_PURCHASE:
		_apply_rate(row, item.last_purchase_rate)
		return

	# an item with no cost source yet: 0, unless a rate was typed in for this tender
	row["cost_from"] = ""
	_apply_rate(row, 0)


def _match_cost_source(row: dict, item_code: str, item) -> bool:
	"""Move a row to the item's default cost source if its current one doesn't suit the item: a
	manufactured item costed from a price or its last purchase rate, or a bought-in item costed
	from a BOM. Returns whether the row changed. A rate typed in for the old source is dropped.

	Defaults (the same as the builder's): a manufactured item's default BOM, else its newest active
	BOM, else nothing (not costed until it has one); a bought-in item's price in a buying price
	list, else its last purchase rate if it has one, else any price, else its last purchase rate.
	"""
	manufactured = item.default_material_request_type == MANUFACTURE_REQUEST_TYPE
	if manufactured:
		if row.get("bom"):
			return False
		bom = frappe.get_all(
			"BOM",
			filters={"item": item_code, "docstatus": 1, "is_active": 1},
			order_by="is_default desc, creation desc",
			pluck="name",
			limit=1,
		)
		source = {"cost_from": COST_FROM_BOM, "bom": bom[0]} if bom else {"cost_from": ""}
		if not bom and not (row.get("price_row") or row.get("cost_from")):
			return False  # already not costed
	else:
		if not row.get("bom"):
			return False
		source = _default_bought_in_source(item_code, item)

	row.update(cost_from="", bom="", price_row="", price_list="", rate_override=0)
	row.update(source)
	return True


def _default_bought_in_source(item_code: str, item) -> dict:
	ItemPrice = frappe.qb.DocType("Item Price")
	PriceList = frappe.qb.DocType("Price List")
	prices = (
		frappe.qb.from_(ItemPrice)
		.inner_join(PriceList)
		.on(PriceList.name == ItemPrice.price_list)
		.select(ItemPrice.name, PriceList.buying)
		.where(ItemPrice.item_code == item_code)
		.where(PriceList.enabled == 1)
		.orderby(PriceList.buying, order=frappe.qb.desc)
		.orderby(ItemPrice.price_list)
		.orderby(ItemPrice.uom)
		.run(as_dict=True)
	)
	if prices and prices[0].buying:
		return {"cost_from": COST_FROM_PRICE_LIST, "price_row": prices[0].name}
	if flt(item.last_purchase_rate) or not prices:
		return {"cost_from": COST_FROM_LAST_PURCHASE}
	return {"cost_from": COST_FROM_PRICE_LIST, "price_row": prices[0].name}


def _bom_unit_cost(bom) -> float:
	"""What one of the BOM's item costs to make: its total cost (materials, operations, less scrap)
	over its quantity."""
	return flt(bom.total_cost) / (flt(bom.quantity) or 1)


def _default_currency() -> str:
	return frappe.db.get_default("currency") or ""


def _validate_and_calculate_other_costs(charges: list[dict]) -> float:
	"""Per-unit charges added by the user in the Other Costs section; returns their total."""
	charges[:] = [c for c in charges if cstr(c.get("description")).strip() or c.get("item_code")]
	total = 0.0
	for charge in charges:
		charge["description"] = cstr(charge.get("description")).strip()
		charge["remark"] = cstr(charge.get("remark")).strip()
		item_code = charge.get("item_code") or ""
		if item_code:
			item_name = frappe.db.get_value("Item", item_code, "item_name")
			if not item_name:
				frappe.throw(_("Item {0} in Other Costs not found.").format(item_code))
			charge["description"] = charge["description"] or item_name
		charge["item_code"] = item_code
		charge["qty"] = flt(charge.get("qty"))
		charge["rate"] = flt(charge.get("rate"))
		if charge["qty"] < 0 or charge["rate"] < 0:
			frappe.throw(_("Qty and rate cannot be negative for {0} in Other Costs.").format(charge["description"]))
		charge["amount"] = charge["qty"] * charge["rate"]
		total += charge["amount"]
	return total


def _apply_rate(row: dict, list_rate: float):
	"""Use the rate from the cost source, unless the rate was changed on the tender (rate_override)."""
	row["list_rate"] = flt(list_rate)
	if cint(row.get("rate_override")) and row.get("item_code"):
		row["rate"] = flt(row.get("rate"))
		if row["rate"] < 0:
			frappe.throw(_("Rate cannot be negative for row {0}.").format(row.get("label")))
		# set back to the list price = no longer an override
		row["rate_override"] = 0 if row["rate"] == row["list_rate"] else 1
	else:
		row["rate"] = row["list_rate"]
		row["rate_override"] = 0
	row["amount"] = flt(row["qty"]) * flt(row["rate"])


def _apply_tender_pricing(doc: PreProductionManifest):
	doc.cost_base = flt(doc.grand_total_cost)
	doc.target_margin_pct = flt(doc.target_margin_pct)
	doc.margin_amount = flt(doc.cost_base) * (flt(doc.target_margin_pct) / 100.0)
	doc.tender_price_total = flt(doc.cost_base) + flt(doc.margin_amount)
	kitchens = flt(doc.kitchens_to_tender or 0)
	doc.tender_price_per_kitchen = flt(doc.tender_price_total) / kitchens if kitchens else 0


@frappe.whitelist()
def get_template_rows(template: str):
	if not template:
		return []
	return _get_template_rows(template)


def _get_template_rows(template: str) -> list[dict]:
	rows = frappe.get_all(
		"Pre Production Manifest Template Row",
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
@frappe.validate_and_sanitize_search_inputs
def bom_query(doctype, txt, searchfield, start, page_len, filters):
	"""Cost From for a manufactured item: its submitted, active BOMs, default first, each with its
	unit cost."""
	item = filters.get("item")
	if not item:
		return []
	stock_uom = frappe.db.get_value("Item", item, "stock_uom")
	boms = frappe.get_all(
		"BOM",
		filters={"item": item, "docstatus": 1, "is_active": 1, "name": ["like", f"%{txt}%"]},
		fields=["name", "is_default", "total_cost", "quantity", "currency"],
		order_by="is_default desc, creation desc",
		limit_start=start,
		limit_page_length=page_len,
	)
	return [
		(
			bom.name,
			" · ".join(
				filter(None, [_("Default") if bom.is_default else "", _money(_bom_unit_cost(bom), bom.currency, stock_uom)])
			),
		)
		for bom in boms
	]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_price_query(doctype, txt, searchfield, start, page_len, filters):
	"""Cost From for a bought-in item: its prices in any enabled price list, buying lists first."""
	item_code = filters.get("item_code")
	if not item_code:
		return []
	ItemPrice = frappe.qb.DocType("Item Price")
	PriceList = frappe.qb.DocType("Price List")
	prices = (
		frappe.qb.from_(ItemPrice)
		.inner_join(PriceList)
		.on(PriceList.name == ItemPrice.price_list)
		.select(ItemPrice.name, ItemPrice.price_list, ItemPrice.price_list_rate, ItemPrice.currency, ItemPrice.uom)
		.where(ItemPrice.item_code == item_code)
		.where(PriceList.enabled == 1)
		# typed text matches the price list; Frappe also re-runs this query with the chosen Item Price's
		# name to validate the pick, so the name has to match too
		.where(ItemPrice.price_list.like(f"%{txt}%") | ItemPrice.name.like(f"%{txt}%"))
		.orderby(PriceList.buying, order=frappe.qb.desc)
		.orderby(ItemPrice.price_list)
		.orderby(ItemPrice.uom)
		.limit(page_len)
		.offset(start)
		.run(as_dict=True)
	)
	return [(p.name, f"{p.price_list} · {_money(p.price_list_rate, p.currency, p.uom)}") for p in prices]


def _money(rate: float, currency: str | None, uom: str | None) -> str:
	return fmt_money(flt(rate), currency=currency) + (f" / {uom}" if uom else "")


@frappe.whitelist()
def get_cost_options(item_codes: str | list) -> dict:
	"""Where each item's cost can come from, for the builder's Cost From picker.

	{item_code: {"manufactured", "stock_uom", "boms": [{name, is_default, unit_cost, currency}],
	"prices": [{price_row, price_list, buying, selling, rate, currency, uom}], "last_purchase_rate"}}.
	An item whose Default Material Request Type is Manufacture is costed from one of its submitted,
	active BOMs; any other item is bought in and costed from a price list or its last purchase rate.
	"""
	if isinstance(item_codes, str):
		item_codes = json.loads(item_codes)
	codes = sorted({c for c in item_codes or [] if c})
	if not codes:
		return {}
	frappe.has_permission("Pre Production Manifest", "read", throw=True)

	options = {
		i.name: {
			"manufactured": i.default_material_request_type == MANUFACTURE_REQUEST_TYPE,
			"stock_uom": i.stock_uom,
			"last_purchase_rate": flt(i.last_purchase_rate),
			"boms": [],
			"prices": [],
		}
		for i in frappe.get_all(
			"Item",
			filters={"name": ["in", codes]},
			fields=["name", "default_material_request_type", "stock_uom", "last_purchase_rate"],
		)
	}
	manufactured = [code for code, o in options.items() if o["manufactured"]]
	bought_in = [code for code, o in options.items() if not o["manufactured"]]
	for bom in frappe.get_all(
		"BOM",
		filters={"item": ["in", manufactured or [""]], "docstatus": 1, "is_active": 1},
		fields=["name", "item", "is_default", "total_cost", "quantity", "currency"],
		order_by="is_default desc, creation desc",
	):
		options[bom.item]["boms"].append(
			{"name": bom.name, "is_default": bom.is_default, "unit_cost": _bom_unit_cost(bom), "currency": bom.currency}
		)

	ItemPrice = frappe.qb.DocType("Item Price")
	PriceList = frappe.qb.DocType("Price List")
	prices = (
		frappe.qb.from_(ItemPrice)
		.inner_join(PriceList)
		.on(PriceList.name == ItemPrice.price_list)
		.select(
			ItemPrice.name.as_("price_row"),
			ItemPrice.item_code,
			ItemPrice.price_list,
			PriceList.buying,
			PriceList.selling,
			ItemPrice.price_list_rate.as_("rate"),
			ItemPrice.currency,
			ItemPrice.uom,
		)
		.where(ItemPrice.item_code.isin(bought_in or [""]))
		.where(PriceList.enabled == 1)
		.orderby(PriceList.buying, order=frappe.qb.desc)
		.orderby(ItemPrice.price_list)
		.orderby(ItemPrice.uom)
		.run(as_dict=True)
	)
	for price in prices:
		options[price.pop("item_code")]["prices"].append(price)
	return options
