# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Excel export of a Tender Manifest, laid out like a contractor's trade bill (BoQ).

Two versions: the detailed bill is the internal costing (cost rates, margin, reference-only specs,
notes); the simplified bill is for the client, priced at tender price with the margin spread over
every line: item lines only, without specs, notes, cost rates, margin or reference-only lines.
"""

import json
import math
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT = "Arial"
MONEY = '#,##0.00;[Red]\\-#,##0.00'
QTY = "#,##0.###"
THIN = Side(style="thin", color="808080")
GRID = Side(style="thin", color="BFBFBF")
HEADER_FILL = PatternFill("solid", fgColor="E7E9ED")
SECTION_FILL = PatternFill("solid", fgColor="F4F5F7")
TOTAL_FILL = PatternFill("solid", fgColor="EEF1F6")
NOTE_FILL = PatternFill("solid", fgColor="FFF8E1")

# Bill columns: gutter | Ref | Description | Qty/Unit | Unit | Rate | € per Unit | € Total
# Spec and note rows span Description → € Total (C:H) under their item.
BILL_WIDTHS = [2, 5, 62, 10, 7, 11, 13, 14]
FIRST_COL, LAST_COL = 2, 8
DESC_CHARS_PER_LINE = 72
WIDE_CHARS_PER_LINE = 125
UNIT_NAMES = {"Nos": "nr", "Meter": "m", "Hour": "hr", "M²": "m²", "HRS/KIT": "hr"}
CABINET_UNITS = (
	("base_units", "Base units"),
	("wall_units", "Wall units"),
	("tall_units", "Tall units"),
	("drawer_packs", "Drawer packs"),
)


@frappe.whitelist()
def download_tender_excel(name: str, simplified: int | str = 0):
	doc = frappe.get_doc("Tender Manifest", name)
	doc.check_permission("read")
	client = bool(int(simplified or 0))

	wb = Workbook()
	bill = wb.active
	bill.title = "Tender Bill"
	summary = wb.create_sheet("Summary")

	header = _header_lines(doc, client)
	section_totals = _write_bill(bill, doc, header, client)
	_write_summary(summary, doc, header, section_totals, client)

	out = BytesIO()
	wb.save(out)
	suffix = " (Simplified)" if client else ""
	frappe.response["filename"] = f"{doc.name} - {doc.tender_name or 'Tender'}{suffix}.xlsx".replace("/", "-")
	frappe.response["filecontent"] = out.getvalue()
	frappe.response["type"] = "binary"


def _header_lines(doc, client: bool = False) -> list[str]:
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	return [
		f"From: {company}" if company else "",
		f"Project: {doc.tender_name}",
		f"Tender: {doc.name}{'' if client else f' · Template: {doc.template}'}"
		f" · Units to tender: {int(flt(doc.kitchens_to_tender))}"
		f" · Date: {formatdate(nowdate())}",
	]


def _write_title(ws, title: str, header: list[str]) -> int:
	ws["B2"] = title
	ws["B2"].font = Font(name=FONT, size=16, bold=True)
	row = 3
	for line in header:
		if line:
			ws.cell(row=row, column=2, value=line).font = Font(name=FONT, size=10)
			row += 1
	return row + 1


def _box_row(ws, row: int, first_col: int, last_col: int, top: Side = GRID, bottom: Side = GRID):
	"""Grid border on every cell of a row, so each line of the bill reads as its own box."""
	for col in range(first_col, last_col + 1):
		ws.cell(row=row, column=col).border = Border(left=GRID, right=GRID, top=top, bottom=bottom)


def _write_bill(
	ws, doc, header, client: bool = False, title: str = "Tender Bill", with_totals: bool = False
) -> list[tuple[str, float, float]]:
	"""Write the priced bill; returns (section name, € per unit, € total) for the summary.

	with_totals adds the cost / margin / tender price lines under the last section, for a bill
	that has no summary sheet of its own (the Tender's workbook).
	"""
	for i, width in enumerate(BILL_WIDTHS, start=1):
		ws.column_dimensions[get_column_letter(i)].width = width

	row = _write_title(ws, title, header)

	# units to tender sits in one cell so every line total refers to it
	ws.cell(row=row, column=3, value="Units to tender").font = Font(name=FONT, size=10, bold=True)
	units = ws.cell(row=row, column=4, value=flt(doc.kitchens_to_tender))
	units.font = Font(name=FONT, size=10, bold=True)
	units.number_format = QTY
	units.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
	unit_count = flt(doc.kitchens_to_tender)
	row += 2

	header_row = row
	for col, label in enumerate(
		["Ref", "Description", "Qty / Unit", "Unit", "Rate", "€ per Unit", "€ Total"], start=FIRST_COL
	):
		cell = ws.cell(row=row, column=col, value=label)
		cell.font = Font(name=FONT, size=10, bold=True)
		cell.fill = HEADER_FILL
		cell.alignment = Alignment(horizontal="right" if col in (4, 6, 7, 8) else "left", vertical="center")
	_box_row(ws, row, FIRST_COL, LAST_COL, top=THIN, bottom=THIN)
	ws.freeze_panes = ws.cell(row=row + 1, column=1)
	row += 1

	section_totals = []
	for number, (section, rows) in enumerate(_group_rows(doc, client), start=1):
		title = ws.cell(row=row, column=FIRST_COL, value=f"({number}) {section.title()}")
		title.font = Font(name=FONT, size=11, bold=True)
		ws.merge_cells(start_row=row, start_column=FIRST_COL, end_row=row, end_column=LAST_COL)
		for col in range(FIRST_COL, LAST_COL + 1):
			ws.cell(row=row, column=col).fill = SECTION_FILL
		_box_row(ws, row, FIRST_COL, LAST_COL, top=THIN, bottom=THIN)
		ws.row_dimensions[row].height = 18
		row += 1

		for ref, line in zip(_refs(), rows):
			row = _write_item(ws, row, ref, line, unit_count, client)
		if not rows:
			row = _write_wide(ws, row, _("No other costs added."), Font(name=FONT, size=9, italic=True, color="808080"))

		# values, not formulas: openpyxl can't store calculated results, so previews and Excel's
		# Protected View would show formula totals as blank/0 until the file is recalculated
		priced = [line for line in rows if not line.get("exclude_from_price")]
		reference_only = bool(rows) and not priced
		# a section of only spec rows gets a reference total; otherwise only priced lines count
		counted = rows if reference_only else priced
		section_per_unit = sum(line["per_unit"] for line in counted)
		section_total = sum(line["total"] for line in counted)
		if not client:
			section_per_unit, section_total = flt(section_per_unit, 2), flt(section_total, 2)
		title = f"{section.title()} total" + (" (reference only, not in tender price)" if reference_only else "")
		label = ws.cell(row=row, column=3, value=title)
		per_unit = ws.cell(row=row, column=7, value=section_per_unit)
		total = ws.cell(row=row, column=8, value=section_total)
		for cell in (label, per_unit, total):
			cell.font = Font(name=FONT, size=10, bold=True, italic=reference_only, color="808080" if reference_only else None)
		for cell in (per_unit, total):
			cell.number_format = MONEY
		for col in range(FIRST_COL, LAST_COL + 1):
			ws.cell(row=row, column=col).fill = TOTAL_FILL
		_box_row(ws, row, FIRST_COL, LAST_COL, top=THIN, bottom=THIN)
		if not reference_only:
			section_totals.append((section.title(), section_per_unit, section_total))
		row += 2

	if with_totals:
		_write_bill_totals(ws, row, doc, client)
	_page_setup(ws, header_row, last_column="H")
	return section_totals


def _write_item(ws, row: int, ref: str, line: dict, unit_count: float, client: bool = False) -> int:
	"""One item block: the priced line, then its spec, then its note, each a full-width row under it.

	The simplified (client) bill has the priced line only.
	"""
	first = row
	row = _write_line(ws, row, line, unit_count, client)

	spec = "" if client else (line.get("specification") or "").strip()
	if spec:
		heading = " · ".join(filter(None, [line.get("spec_list"), line.get("spec_reference")]))
		if heading and line.get("spec_custom"):
			heading += ", edited for this tender"
		text = f"Specification{f' ({heading})' if heading else ''}:\n{spec}"
		row = _write_wide(ws, row, text, Font(name=FONT, size=9, color="404040"))

	note = "" if client else (line.get("remark") or "").strip()
	if note:
		row = _write_wide(ws, row, f"Note: {note}", Font(name=FONT, size=9, italic=True), fill=NOTE_FILL)

	# the ref spans the whole block, with a darker rule above it, so each item is easy to pick out
	ref_cell = ws.cell(row=first, column=FIRST_COL, value=ref)
	ref_cell.font = Font(name=FONT, size=10, bold=True)
	ref_cell.alignment = Alignment(horizontal="center", vertical="top")
	if row - 1 > first:
		ws.merge_cells(start_row=first, start_column=FIRST_COL, end_row=row - 1, end_column=FIRST_COL)
	for col in range(FIRST_COL, LAST_COL + 1):
		cell = ws.cell(row=first, column=col)
		cell.border = Border(left=cell.border.left, right=cell.border.right, top=THIN, bottom=cell.border.bottom)
	for r in range(first, row):
		cell = ws.cell(row=r, column=FIRST_COL)
		cell.border = Border(left=GRID, right=GRID, top=THIN if r == first else GRID, bottom=GRID)
	return row


def _write_line(ws, row: int, line: dict, unit_count: float, client: bool = False) -> int:
	item = line.get("item_name") or line.get("item_code") or _("Not selected")
	excluded = bool(line.get("exclude_from_price"))
	if line.get("is_charge"):
		# a charge's description is its own wording; show the item only if it adds something
		item = line.get("item_name") or line.get("item_code") or ""
		head = line.get("label") if not item or item == line.get("label") else f"{line.get('label')} ({item})"
	else:
		head = f"{line.get('label')}: {item}"
	description = (
		head
		+ (" (rate adjusted)" if line.get("rate_override") and not client else "")
		+ (" (not in tender price)" if excluded else "")
	)
	# the row amount the server saved on the tender, so the bill matches the form exactly;
	# spec-only rows show their cost for reference but are left out of the totals
	if client:
		# marked-up values unrounded (the cells show 2dp), so the sections add up to the tender price
		line["per_unit"] = flt(line.get("amount"))
		line["total"] = line["per_unit"] * unit_count
	else:
		line["per_unit"] = flt(line.get("amount"), 2)
		line["total"] = flt(line["per_unit"] * unit_count, 2)

	values = {
		3: description,
		4: flt(line.get("qty")),
		5: _unit(line),
		6: flt(line.get("rate")) or None,
		7: line["per_unit"],
		8: line["total"],
	}
	for col, value in values.items():
		cell = ws.cell(row=row, column=col, value=value)
		cell.font = Font(name=FONT, size=10)
		cell.alignment = Alignment(vertical="top", wrap_text=col == 3)
	ws.cell(row=row, column=4).number_format = QTY
	for col in (6, 7, 8):
		ws.cell(row=row, column=col).number_format = MONEY
	if excluded:
		for col in (3, 4, 5, 6, 7, 8):
			ws.cell(row=row, column=col).font = Font(name=FONT, size=10, italic=True, color="808080")

	_box_row(ws, row, FIRST_COL, LAST_COL)
	ws.row_dimensions[row].height = _height(description, DESC_CHARS_PER_LINE, 13)
	return row + 1


def _write_wide(ws, row: int, text: str, font: Font, fill: PatternFill | None = None) -> int:
	"""A full-width row under an item (Description → € Total), used for its spec and note."""
	cell = ws.cell(row=row, column=3, value=text)
	cell.font = font
	cell.alignment = Alignment(wrap_text=True, vertical="top")
	ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=LAST_COL)
	if fill:
		for col in range(3, LAST_COL + 1):
			ws.cell(row=row, column=col).fill = fill
	_box_row(ws, row, FIRST_COL, LAST_COL)
	ws.row_dimensions[row].height = _height(text, WIDE_CHARS_PER_LINE, 11.5)
	return row + 1


def _write_summary(ws, doc, header, section_totals, client: bool = False):
	for i, width in enumerate([2, 40, 18, 18], start=1):
		ws.column_dimensions[get_column_letter(i)].width = width

	row = _write_title(ws, "Tender Summary", header)
	for col, label in enumerate(["Section", "€ per Unit", "€ Total"], start=2):
		cell = ws.cell(row=row, column=col, value=label)
		cell.font = Font(name=FONT, size=10, bold=True)
		cell.fill = HEADER_FILL
		cell.alignment = Alignment(horizontal="left" if col == 2 else "right")
	_box_row(ws, row, 2, 4, top=THIN, bottom=THIN)
	header_row = row
	row += 1

	first = row
	for section, per_unit, total in section_totals:
		ws.cell(row=row, column=2, value=section)
		ws.cell(row=row, column=3, value=per_unit)
		ws.cell(row=row, column=4, value=total)
		_box_row(ws, row, 2, 4)
		row += 1

	for label, per_unit, total, bold in _price_lines(doc, client):
		ws.cell(row=row, column=2, value=label)
		ws.cell(row=row, column=3, value=per_unit)
		ws.cell(row=row, column=4, value=total)
		for col in (2, 3, 4):
			ws.cell(row=row, column=col).font = Font(name=FONT, size=10, bold=bold)
		if label == "Tender price":
			for col in (2, 3, 4):
				ws.cell(row=row, column=col).fill = TOTAL_FILL
			_box_row(ws, row, 2, 4, top=THIN, bottom=Side(style="double", color="808080"))
		else:
			_box_row(ws, row, 2, 4, top=THIN if label.startswith("Cost") else GRID)
		row += 1

	for r in range(first, row):
		for col in (3, 4):
			ws.cell(row=r, column=col).number_format = MONEY
		for col in (2, 3, 4):
			if not ws.cell(row=r, column=col).font.bold:
				ws.cell(row=r, column=col).font = Font(name=FONT, size=10)

	_page_setup(ws, header_row, last_column="D")


def _price_lines(doc, client: bool = False) -> list[tuple[str, float, float, bool]]:
	"""(label, € per unit, € total, bold) for the closing lines: cost and margin, then tender price.

	The tender's own saved figures, unrounded: Excel's 2dp format then shows them exactly as the
	form does (half-cents up), whereas flt(x, 2) would apply banker's rounding and be a cent off.
	"""
	units = flt(doc.kitchens_to_tender)
	lines = [] if client else [
		("Cost per unit / Cost base", flt(doc.total_cost_per_kitchen), flt(doc.cost_base), True),
		(
			f"Margin ({flt(doc.target_margin_pct):g}% on cost)",
			flt(doc.margin_amount) / units if units else 0,
			flt(doc.margin_amount),
			False,
		),
	]
	lines.append(("Tender price", flt(doc.tender_price_per_kitchen), flt(doc.tender_price_total), True))
	return lines


def _write_bill_totals(ws, row: int, doc, client: bool = False) -> int:
	"""The closing cost / margin / tender price lines under a bill (used on the Tender's workbook)."""
	for label, per_unit, total, bold in _price_lines(doc, client):
		is_price = label == "Tender price"
		cells = (
			ws.cell(row=row, column=3, value=label),
			ws.cell(row=row, column=7, value=per_unit),
			ws.cell(row=row, column=8, value=total),
		)
		for cell in cells:
			cell.font = Font(name=FONT, size=10, bold=bold)
		for cell in cells[1:]:
			cell.number_format = MONEY
		if is_price:
			for col in range(FIRST_COL, LAST_COL + 1):
				ws.cell(row=row, column=col).fill = TOTAL_FILL
		_box_row(
			ws, row, FIRST_COL, LAST_COL,
			top=THIN if is_price or label.startswith("Cost") else GRID,
			bottom=Side(style="double", color="808080") if is_price else GRID,
		)
		row += 1
	return row


def _group_rows(doc, client: bool = False) -> list[tuple[str, list[dict]]]:
	rows = json.loads(doc.config_rows_json or "[]")
	item_names = dict(
		frappe.get_all(
			"Item",
			filters={"name": ["in", [r["item_code"] for r in rows if r.get("item_code")]]},
			fields=["name", "item_name"],
			as_list=True,
		)
	)

	grouped: dict[str, list[dict]] = {}
	cabinet_units = _cabinet_unit_lines(doc)
	if cabinet_units:
		# priced from the template's cabinet prices; included so the bill total matches the tender
		grouped["CABINET UNITS"] = cabinet_units
	for line in rows:
		line["item_name"] = item_names.get(line.get("item_code"))
		grouped.setdefault(line.get("section") or "Items", []).append(line)

	# charges added in the Other Costs section (per unit, priced like any other line); the
	# section is always shown, like on the form, even when no charges were added
	charges = json.loads(doc.other_costs_json or "[]")
	grouped["OTHER COSTS"] = [
		{
			"label": charge.get("description") or charge.get("item_code"),
			"item_code": charge.get("item_code"),
			"item_name": frappe.db.get_value("Item", charge["item_code"], "item_name") if charge.get("item_code") else None,
			"qty": charge.get("qty"),
			"rate": charge.get("rate"),
			"amount": charge.get("amount"),
			"remark": charge.get("remark"),
			"is_charge": 1,
		}
		for charge in charges
	]
	if not client:
		return list(grouped.items())

	# simplified (client) version: priced lines only, each at tender price (the margin spread over
	# every line)
	markup = _markup(doc)
	client_groups = []
	for section, lines in grouped.items():
		priced = [line for line in lines if not line.get("exclude_from_price")]
		for line in priced:
			line["rate"] = flt(line.get("rate")) * markup
			line["amount"] = flt(line.get("amount")) * markup
		if priced:
			client_groups.append((section, priced))
	return client_groups


def _markup(doc) -> float:
	"""Tender price over cost, so marked-up lines add up to the tender price exactly."""
	cost = flt(doc.cost_base)
	return flt(doc.tender_price_total) / cost if cost else 1 + flt(doc.target_margin_pct) / 100


def _cabinet_unit_lines(doc) -> list[dict]:
	prices = json.loads(doc.cabinet_prices_json or "{}")
	lines = []
	for key, label in CABINET_UNITS:
		qty = flt(doc.get(key))
		if not qty:
			continue
		price = prices.get(key) or {}
		lines.append(
			{
				"label": label,
				"item_code": price.get("item_code"),
				"item_name": frappe.db.get_value("Item", price.get("item_code"), "item_name"),
				"qty": qty,
				"rate": flt(doc.get(f"{key}_rate")),
				"amount": flt(doc.get(f"{key}_amount")),
				"uom": price.get("uom"),
			}
		)
	return lines


def _refs():
	"""A, B, C … like the bill (skipping I and O, which read as numbers), then AA, AB …"""
	letters = [c for c in "ABCDEFGHJKLMNPQRSTUVWXYZ"]
	yield from letters
	for first in letters:
		for second in letters:
			yield first + second


def _unit(line: dict) -> str:
	"""Unit the line is priced in: the price's own UOM (m, hr), or the template's qty label for 'Nos' prices."""
	uom = line.get("uom")
	qty_label = line.get("qty_label")
	if uom and uom != "Nos":
		return UNIT_NAMES.get(uom, uom)
	if qty_label and qty_label != "QTY":
		return UNIT_NAMES.get(qty_label, qty_label)
	return UNIT_NAMES.get(uom, uom or "nr")


def _height(text: str, chars_per_line: int, line_height: float) -> float:
	"""Row height for wrapped text (Excel doesn't auto-fit rows written by openpyxl)."""
	lines = sum(max(1, math.ceil(len(part) / chars_per_line)) for part in (text or "").split("\n"))
	return max(15, lines * line_height + 3)


def _page_setup(ws, header_row: int, last_column: str):
	ws.sheet_view.showGridLines = False
	ws.page_setup.orientation = "landscape"
	ws.page_setup.paperSize = ws.PAPERSIZE_A4
	ws.page_setup.fitToWidth = 1
	ws.page_setup.fitToHeight = 0
	ws.sheet_properties.pageSetUpPr.fitToPage = True
	ws.print_title_rows = f"{header_row}:{header_row}"
	ws.print_area = f"A1:{last_column}{ws.max_row}"
	ws.oddFooter.center.text = "Page &P of &N"
	ws.oddFooter.right.text = f"Printed {formatdate(getdate())}"
