# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Units tab of a won Tender: the units table, its workbook, a preview and project creation.

The Units table has a row per apartment per manifest (Apt Type, Floor, Apt No, Unit Name, Manifest,
Qty); rows sharing an Apt No are one apartment. The workbook is the same table in Excel, for bulk
editing: uploading it fills the table. Creating projects builds what the rest of the project module
expects: a Site project, a Project Unit Configuration per apartment type with production Manifests,
and per apartment a Kitchen project with its other manifests (Robe, Utility...) under it.
"""

import json
import re
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, formatdate, nowdate
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_manifest.tender_manifest_excel import (
	FONT,
	HEADER_FILL,
	THIN,
	_box_row,
)
from fitzgerald_kitchens.setup.manifest_line_labels import resolve_label_category, resolve_manifest_linked_bom
from fitzgerald_kitchens.setup.project_unit_fields import KITCHEN_PROJECT_TYPE, SITE_PROJECT_TYPE
from fitzgerald_kitchens.workbook_import.naming import (
	build_configuration_code,
	build_configuration_display_name,
	build_unit_project_name,
	normalize_site_scope,
)

TENDER_SHEET = "Tender"
UNITS_SHEET = "Units"
LISTS_SHEET = "Lists"
# the Units sheet: these, then a "<Project Type> Manifest" + "<Project Type> Qty" pair per project type
BASE_HEADERS = ["Apt Type", "Floor", "Apt No", "Unit Name"]
UNIT_FIELDS = ["unit_type", "floor", "number", "unit_name", "manifest", "qty"]
MANIFEST_HEADERS = ["Section", "Label", "Item Code", "Item Name", "Qty per Unit", "UOM", "Specification"]
SITE_NAME_CELL = "B6"
EDIT_FILL = PatternFill("solid", fgColor="FFF8E1")

# project type -> Manifest.manifest_category / Project Unit Configuration slot
MANIFEST_CATEGORY = {"Kitchen": "Kitchen", "Robe": "Robe", "Utility": "Utility", "Vanity Unit": "Vanity", "Pantry": "Pantry"}
CONFIGURATION_SLOT = {
	"Kitchen": "kitchen_utility_manifest",
	"Robe": "wardrobe_manifest",
	"Vanity Unit": "vanity_unit_manifest",
	"Pantry": "pantry_manifest",
}


# ---------------------------------------------------------------- workbook: download


@frappe.whitelist()
def download_unit_workbook(tender: str):
	doc = _get_won_tender(tender, "read")
	manifests = _tender_manifests(doc.name)
	if not manifests:
		frappe.throw(_("This tender has no manifests."))
	project_types = _project_types(manifests)

	wb = Workbook()
	_write_tender_sheet(wb.active, doc, project_types)
	lists = wb.create_sheet(LISTS_SHEET)
	_write_units_sheet(wb.create_sheet(UNITS_SHEET), doc, manifests, project_types, lists)
	taken = [TENDER_SHEET, UNITS_SHEET, LISTS_SHEET]
	for number, m in enumerate(manifests, start=1):
		# the sheet shows what the manifest contains; its ID is at the top
		taken.append(_sheet_name(number, f"{_(m.project_type or KITCHEN_PROJECT_TYPE)} - {m.tender_name or m.name}", taken))
		_write_manifest_sheet(wb.create_sheet(taken[-1]), m)
	lists.sheet_state = "hidden"
	wb.active = wb.sheetnames.index(UNITS_SHEET)

	out = BytesIO()
	wb.save(out)
	frappe.response["filename"] = f"{doc.name} - {doc.tender_name} - Units.xlsx".replace("/", "-")
	frappe.response["filecontent"] = out.getvalue()
	frappe.response["type"] = "binary"


def _write_tender_sheet(ws, doc, project_types):
	ws.title = TENDER_SHEET
	ws.column_dimensions["A"].width = 22
	ws.column_dimensions["B"].width = 26
	ws["A1"] = _("Unit Workbook")
	ws["A1"].font = Font(name=FONT, size=16, bold=True)
	rows = [
		(_("Tender"), doc.name),
		(_("Tender Name"), doc.tender_name),
		(_("Party"), f"{doc.party_type}: {doc.party_title or doc.party_name}" if doc.party_name else ""),
		(_("Site Name"), _site_name(doc)),
		(_("Number of Units"), cint(doc.number_of_units) or ""),
		(_("Generated"), formatdate(nowdate())),
	]
	for i, (label, value) in enumerate(rows, start=3):
		ws.cell(row=i, column=1, value=label).font = Font(name=FONT, size=10, bold=True)
		ws.cell(row=i, column=2, value=value).font = Font(name=FONT, size=10)
	ws[SITE_NAME_CELL].fill = EDIT_FILL
	_write_how_to(ws, 10, project_types)


def _write_how_to(ws, start: int, project_types):
	"""How to fill in the Units sheet, with a worked example (here, so it's never read as data)."""
	bold, plain = Font(name=FONT, size=10, bold=True), Font(name=FONT, size=10)
	ws.cell(row=start, column=1, value=_("How to fill in the Units sheet")).font = Font(name=FONT, size=12, bold=True)
	steps = [
		_("1. One row per apartment. Apt Type: e.g. 1B2P. Floor: e.g. 1 or G. Apt No: e.g. 101, unique on the site. Unit Name: optional plot / address."),
		_("2. For each project type, pick the apartment's manifest from the list in its Manifest column, and enter how many in its Qty column (blank = 1). Leave both blank if the apartment doesn't have one."),
		_("3. Every apartment needs a Kitchen manifest. Its other manifests (Robe, Utility, Vanity Unit, Pantry) become projects under the kitchen."),
		_("4. The sheets after Units show what each manifest contains. Leave the Units sheet's header row as it is."),
		_("5. Save, then attach the file on the tender's Units tab: it replaces the Units table, after the same checks as the table."),
	]
	row = start + 1
	for step in steps:
		ws.cell(row=row, column=1, value=step).font = plain
		ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=10)
		ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
		ws.row_dimensions[row].height = 28
		row += 1

	row += 1
	ws.cell(row=row, column=1, value=_("Example: apartments 101 and 102, each with a kitchen and two robes; 201 with a kitchen only")).font = bold
	example_types = project_types[:2] if len(project_types) > 1 else project_types
	headers = BASE_HEADERS + [h for pt in example_types for h in _type_headers(pt)]
	row += 1
	for col, label in enumerate(headers, start=1):
		cell = ws.cell(row=row, column=col, value=label)
		cell.font = bold
		cell.fill = HEADER_FILL
	_box_row(ws, row, 1, len(headers), top=THIN, bottom=THIN)
	samples = [("1B2P", "1", "101", "Plot 1", True), ("1B2P", "1", "102", "Plot 2", True), ("2B4P", "2", "201", "", False)]
	for apt_type, floor, number, name, other in samples:
		row += 1
		values = [apt_type, floor, number, name]
		for i, pt in enumerate(example_types):
			has = i == 0 or other
			values += [f"<{_('a {0} manifest').format(_(pt))}>" if has else None, (1 if i == 0 else 2) if has else None]
		for col, value in enumerate(values, start=1):
			ws.cell(row=row, column=col, value=value or None).font = plain
		_box_row(ws, row, 1, len(headers))
	for col in range(3, len(headers) + 1):
		ws.column_dimensions[get_column_letter(col)].width = max(ws.column_dimensions[get_column_letter(col)].width or 0, 14)


def _write_units_sheet(ws, doc, manifests, project_types, lists):
	headers = BASE_HEADERS + [h for pt in project_types for h in _type_headers(pt)]
	widths = [12, 8, 10, 28] + [w for _pt in project_types for w in (34, 8)]
	for col, (label, width) in enumerate(zip(headers, widths), start=1):
		cell = ws.cell(row=1, column=col, value=label)
		cell.font = Font(name=FONT, size=10, bold=True)
		cell.fill = HEADER_FILL
		cell.alignment = Alignment(vertical="center", wrap_text=True)
		ws.column_dimensions[get_column_letter(col)].width = width
	_box_row(ws, 1, 1, len(headers), top=THIN, bottom=THIN)
	ws.freeze_panes = "E2"

	# the table's apartments, one row each, their manifests across
	labels = {m.name: _manifest_label(m) for m in manifests}
	apartments: dict[str, dict] = {}
	for r in doc.get("unit_types") or []:
		apt = apartments.setdefault((r.number or "").upper(), {"values": [r.unit_type, r.floor, r.number, r.unit_name], "types": {}})
		apt["types"][r.project_type or KITCHEN_PROJECT_TYPE] = (labels.get(r.manifest, r.manifest), cint(r.qty) or 1)
	row = 2
	for apt in apartments.values():
		values = list(apt["values"])
		for pt in project_types:
			manifest, qty = apt["types"].get(pt, (None, None))
			values += [manifest, qty]
		for col, value in enumerate(values, start=1):
			ws.cell(row=row, column=col, value=value or None).font = Font(name=FONT, size=10)
		_box_row(ws, row, 1, len(headers))
		row += 1
	last = max(row, 2) + 500
	for r in range(2, last):
		for col in range(1, len(headers) + 1):
			ws.cell(row=r, column=col).fill = EDIT_FILL

	# each project type's Manifest column offers that type's manifests
	for i, pt in enumerate(project_types):
		options = [labels[m.name] for m in manifests if (m.project_type or KITCHEN_PROJECT_TYPE) == pt]
		list_col = get_column_letter(i + 1)
		lists.cell(row=1, column=i + 1, value=pt)
		for n, label in enumerate(options, start=2):
			lists.cell(row=n, column=i + 1, value=label)
		dv = DataValidation(type="list", formula1=f"={LISTS_SHEET}!${list_col}$2:${list_col}${len(options) + 1}", allow_blank=True)
		ws.add_data_validation(dv)
		manifest_col = get_column_letter(len(BASE_HEADERS) + 1 + i * 2)
		dv.add(f"{manifest_col}2:{manifest_col}{last}")


def _write_manifest_sheet(ws, m):
	"""What a manifest contains, for reference while filling in the Units sheet."""
	ws["A1"] = f"{m.name} · {m.tender_name or ''}"
	ws["A1"].font = Font(name=FONT, size=14, bold=True)
	ws["A2"] = _("{0} manifest. Reference only: pick it on the Units sheet; its items come from the tender manifest in the system.").format(_(m.project_type or KITCHEN_PROJECT_TYPE))
	ws["A2"].font = Font(name=FONT, size=9, italic=True, color="808080")
	for col, (label, width) in enumerate(zip(MANIFEST_HEADERS, [18, 26, 18, 34, 12, 8, 60]), start=1):
		cell = ws.cell(row=4, column=col, value=label)
		cell.font = Font(name=FONT, size=10, bold=True)
		cell.fill = HEADER_FILL
		ws.column_dimensions[get_column_letter(col)].width = width
	doc = frappe.get_doc("Tender Manifest", m.name)
	row = 5
	for line in _manifest_rows(doc):
		values = [line["section"], line["label"], line["item_code"], line["item_name"], line["qty"], line["uom"], line["specification"]]
		for col, value in enumerate(values, start=1):
			cell = ws.cell(row=row, column=col, value=value)
			cell.font = Font(name=FONT, size=10)
			cell.alignment = Alignment(vertical="top", wrap_text=col == 7)
		row += 1
	charges = json.loads(doc.other_costs_json or "[]")
	if charges:
		ws.cell(row=row + 1, column=1, value=_("Other costs (priced in the tender, not in the manifest)")).font = Font(name=FONT, size=10, bold=True)
		for i, charge in enumerate(charges, start=row + 2):
			ws.cell(row=i, column=1, value=charge.get("description") or charge.get("item_code"))
			ws.cell(row=i, column=5, value=flt(charge.get("qty")))


# ---------------------------------------------------------------- workbook: upload


@frappe.whitelist()
def upload_unit_workbook(tender: str) -> dict:
	"""Read the attached workbook's Units sheet into the Units table (replacing it), if it passes the checks."""
	doc = _get_won_tender(tender, "write")
	if not doc.unit_workbook:
		frappe.throw(_("Attach the unit workbook first."))
	try:
		content = frappe.get_doc("File", {"file_url": doc.unit_workbook}).get_content()
		wb = load_workbook(BytesIO(content), data_only=True)
	except Exception:
		return {"errors": [_("The file couldn't be read as an Excel workbook (.xlsx).")], "warnings": []}
	if UNITS_SHEET not in wb.sheetnames:
		return {"errors": [_("Sheet {0} is missing; download the workbook from the tender and fill that in.").format(frappe.bold(UNITS_SHEET))], "warnings": []}

	ws = wb[UNITS_SHEET]
	headers = [cstr(c.value).strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]
	missing = [h for h in BASE_HEADERS if h not in headers]
	project_types = [h[: -len(" Manifest")] for h in headers if h.endswith(" Manifest")]
	if missing or not project_types:
		return {"errors": [_("The Units sheet's header row has been changed; download a fresh workbook.")], "warnings": []}

	manifests = {m.name: m for m in _tender_manifests(doc.name)}
	errors, rows, seen = [], [], set()
	wanted = BASE_HEADERS + [h for pt in project_types for h in _type_headers(pt)]
	for n, values in _rows(ws, wanted):
		number = _text(values["Apt No"])
		at = _("Units row {0}").format(n)
		if number and number.upper() in seen:
			errors.append(_("{0}: Apt No {1} is on more than one row; one row per apartment.").format(at, frappe.bold(number)))
			continue
		seen.add(number.upper())
		base = {"unit_type": cstr(values["Apt Type"]).strip(), "floor": _text(values["Floor"]), "number": number,
		        "unit_name": cstr(values["Unit Name"]).strip()}
		picked = 0
		for pt in project_types:
			manifest = cstr(values[f"{pt} Manifest"]).split(" · ")[0].strip()
			if not manifest:
				continue
			picked += 1
			m = manifests.get(manifest)
			if m and (m.project_type or KITCHEN_PROJECT_TYPE) != pt:
				errors.append(_("{0}: {1} is a {2} manifest, not {3}.").format(at, frappe.bold(manifest), _(m.project_type), _(pt)))
				continue
			qty = _whole_number(values.get(f"{pt} Qty"), 1)
			rows.append({**base, "manifest": manifest, "qty": qty if qty is not None else -1,
			             "_where": _("{0} ({1})").format(at, _(pt))})
		if not picked:
			errors.append(_("{0}: Apt {1} has no manifests.").format(at, frappe.bold(number or "-")))
	site_name = cstr(wb[TENDER_SHEET][SITE_NAME_CELL].value).strip() if TENDER_SHEET in wb.sheetnames else ""

	plan = _plan(doc, rows, site_name or _site_name(doc), where=lambda r: r["_where"])
	plan["errors"] = errors + plan["errors"]
	if plan["errors"]:
		plan["status"] = "Failed"
		return plan

	doc.set("unit_types", [{k: r[k] for k in UNIT_FIELDS} for r in rows])
	if site_name:
		doc.unit_site_name = site_name
	if doc.unit_import_status != "Completed":
		doc.unit_import_status = "Ready"
	doc.save()
	plan["status"] = "Ready"
	plan["loaded"] = len(seen)
	return plan


def _project_types(manifests) -> list[str]:
	"""Project types the tender's manifests cover, Kitchen first."""
	types = {m.project_type or KITCHEN_PROJECT_TYPE for m in manifests}
	return sorted(types, key=lambda pt: (pt != KITCHEN_PROJECT_TYPE, pt))


def _type_headers(project_type: str) -> list[str]:
	return [f"{project_type} Manifest", f"{project_type} Qty"]


# ---------------------------------------------------------------- units editor page


@frappe.whitelist()
def get_unit_editor(tender: str) -> dict:
	"""Everything the Tender Units page needs: the tender, its manifests, the apartments and their state."""
	doc = _get_won_tender(tender, "read")
	manifests = _tender_manifests(doc.name)
	rows = [{**{k: r.get(k) for k in UNIT_FIELDS}, "_row": r.idx} for r in doc.get("unit_types") or []]
	plan = _plan(doc, rows, _site_name(doc), where=_where_apartment)
	sync = {a["number"].upper(): {"sync": a.get("sync"), "changes": a.get("changes")} for a in plan["apartments"]}

	apartments: dict[str, dict] = {}
	for r in doc.get("unit_types") or []:
		key = (r.number or "").upper()
		apt = apartments.setdefault(key, {"number": r.number, "type": r.unit_type or "", "floor": r.floor or "",
		                                  "name": r.unit_name or "", "manifests": {}, **sync.get(key, {})})
		apt["manifests"][r.project_type or KITCHEN_PROJECT_TYPE] = {"manifest": r.manifest, "qty": cint(r.qty) or 1}
	return {
		"tender": {
			"name": doc.name, "tender_name": doc.tender_name, "party": doc.party_title or doc.party_name,
			"party_type": doc.party_type, "project": doc.project, "status": doc.unit_import_status,
			"site_name": _site_name(doc), "number_of_units": cint(doc.number_of_units),
			"can_write": doc.has_permission("write"), "can_create_projects": frappe.has_permission("Project", "create"),
		},
		"manifests": [{"name": m.name, "label": _manifest_label(m), "project_type": m.project_type or KITCHEN_PROJECT_TYPE} for m in manifests],
		"project_types": _project_types(manifests),
		"apartments": list(apartments.values()),
		"errors": plan["errors"],
		"warnings": plan["warnings"],
		"sync": plan["sync"],
		"not_in_table": plan["not_in_table"],
	}


@frappe.whitelist()
def save_unit_editor(tender: str, apartments: str | list) -> dict:
	"""Save the page's apartments into the Units table (a row per apartment per manifest), if they pass the checks."""
	doc = _get_won_tender(tender, "write")
	if isinstance(apartments, str):
		apartments = json.loads(apartments)
	rows, errors, seen = [], [], set()
	for i, apt in enumerate(apartments, start=1):
		number = cstr(apt.get("number")).strip()
		# a missing or repeated Apt No is reported once here, and the apartment left out of the row checks
		if not number:
			errors.append(_("Apartment #{0} has no Apt No.").format(i))
			continue
		if number.upper() in seen:
			errors.append(_("Apt No {0} is used twice.").format(frappe.bold(number)))
			continue
		seen.add(number.upper())
		manifests = {pt: m for pt, m in (apt.get("manifests") or {}).items() if (m or {}).get("manifest")}
		if not manifests:
			errors.append(_("Apt {0} has no manifests.").format(frappe.bold(number)))
			continue
		base = {"unit_type": cstr(apt.get("type")).strip(), "floor": cstr(apt.get("floor")).strip(), "number": number,
		        "unit_name": cstr(apt.get("name")).strip(), "_where": _("Apt {0}").format(frappe.bold(number))}
		for m in manifests.values():
			qty = _whole_number(m.get("qty"), 1)
			rows.append({**base, "manifest": m["manifest"], "qty": qty if qty is not None else -1})
	plan = _plan(doc, rows, _site_name(doc), where=lambda r: r["_where"])
	errors += plan["errors"]
	if errors:
		return {"ok": False, "errors": errors}
	doc.set("unit_types", [{k: r[k] for k in UNIT_FIELDS} for r in rows])
	if doc.unit_import_status not in ("Completed", "Creating"):
		doc.unit_import_status = "Ready"
	doc.save()
	return {"ok": True, **get_unit_editor(doc.name)}


# ---------------------------------------------------------------- preview


@frappe.whitelist()
def preview_units(tender: str) -> dict:
	"""What Create Projects would build from the Units table, with errors and warnings."""
	doc = _get_won_tender(tender, "read")
	rows = [{**{k: r.get(k) for k in UNIT_FIELDS}, "_row": r.idx} for r in doc.get("unit_types") or []]
	plan = _plan(doc, rows, _site_name(doc), where=_where_apartment)
	status = "Failed" if plan["errors"] else "Ready"
	if doc.unit_import_status not in ("Creating", "Completed") or plan["errors"]:
		frappe.db.set_value("Tender", doc.name, "unit_import_status", status, update_modified=False)
	plan["status"] = status
	return plan


def _where_apartment(r: dict) -> str:
	"""Where a Units table row's error is: its apartment, as the table itself is hidden."""
	return _("Apt {0}").format(frappe.bold(r.get("number"))) if r.get("number") else _("Units row {0}").format(r["_row"])


def _plan(doc, rows: list[dict], site_name: str, where) -> dict:
	"""Group the unit rows into apartments and check them; the same checks for the table and the file."""
	errors, warnings = [], []
	manifests = {m.name: m for m in _tender_manifests(doc.name)}
	if not rows:
		errors.append(_("There are no units yet. Add them with Add Units, or upload the workbook."))

	apartments: dict[str, dict] = {}
	for r in rows:
		at = where(r)
		number = cstr(r.get("number")).strip()
		if not number:
			errors.append(_("{0}: Apt No is required.").format(at))
			continue
		if not cstr(r.get("unit_type")).strip():
			errors.append(_("{0}: Apt Type is required.").format(at))
		m = manifests.get(r.get("manifest"))
		if not m:
			errors.append(_("{0}: {1} isn't one of this tender's manifests.").format(at, frappe.bold(r.get("manifest") or "-")))
			continue
		if cint(r.get("qty")) <= 0:
			errors.append(_("{0}: Qty must be a whole number, at least 1.").format(at))
		project_type = m.project_type or KITCHEN_PROJECT_TYPE
		apt = apartments.setdefault(number.upper(), {
			"number": number, "type": cstr(r.get("unit_type")).strip(), "floor": cstr(r.get("floor")).strip(),
			"name": cstr(r.get("unit_name")).strip(), "rows": {},
		})
		for field, key, label in (("unit_type", "type", _("Apt Type")), ("floor", "floor", _("Floor")), ("unit_name", "name", _("Unit Name"))):
			if cstr(r.get(field)).strip() != apt[key]:
				errors.append(_("{0}: Apt {1} has a different {2} on another row.").format(at, frappe.bold(number), label))
		if project_type in apt["rows"]:
			errors.append(_("{0}: Apt {1} has two {2} manifests; use Qty for more than one.").format(at, frappe.bold(number), project_type))
		apt["rows"][project_type] = {"manifest": m.name, "qty": cint(r.get("qty")) or 1}

	for apt in apartments.values():
		if apt["rows"] and KITCHEN_PROJECT_TYPE not in apt["rows"]:
			errors.append(_("Apt {0} needs a Kitchen manifest; its other manifests are created under the kitchen.").format(frappe.bold(apt["number"])))

	if cint(doc.number_of_units) and len(apartments) != cint(doc.number_of_units):
		warnings.append(_("There are {0} apartments; the tender's Number of Units is {1}.").format(len(apartments), cint(doc.number_of_units)))
	site = frappe.db.get_value("Project", {"project_type": SITE_PROJECT_TYPE, "project_name": site_name}, ["name", "fk_tender"], as_dict=True)
	if site and site.fk_tender and site.fk_tender != doc.name:
		errors.append(_("Site project {0} already belongs to tender {1}. Change the Site Name.").format(frappe.bold(site_name), site.fk_tender))
	sync = _sync_state(site.name if site else None, site_name, apartments)

	order = lambda pt: (pt != KITCHEN_PROJECT_TYPE, pt)
	counts: dict[str, int] = {}
	types: dict[str, dict] = {}
	for apt in apartments.values():
		t = types.setdefault(apt["type"], {"code": apt["type"], "apartments": 0, "manifests": {}})
		t["apartments"] += 1
		for project_type, row in apt["rows"].items():
			counts[project_type] = counts.get(project_type, 0) + 1
			used = t["manifests"].setdefault(row["manifest"], {"project_type": project_type, "manifest": row["manifest"],
			                                                   "manifest_name": manifests[row["manifest"]].tender_name, "apartments": 0})
			used["apartments"] += 1
	return {
		"errors": errors,
		"warnings": warnings,
		"site_name": site_name,
		"site_exists": bool(site),
		"party_is_lead": doc.party_type == "Lead",
		"party": doc.party_title or doc.party_name,
		"types": [
			{**t, "manifests": sorted(t["manifests"].values(), key=lambda m: (order(m["project_type"]), m["manifest"]))}
			for t in types.values()
		],
		"apartments": [
			{**a, "rows": [{"project_type": pt, **row} for pt, row in sorted(a["rows"].items(), key=lambda kv: order(kv[0]))]}
			for a in apartments.values()
		],
		"site": site.name if site else None,
		"project_types": sorted(counts, key=order),
		"project_counts": {pt: counts[pt] for pt in sorted(counts, key=order)},
		"project_total": sum(counts.values()),
		"sync": sync["counts"],
		"not_in_table": sync["not_in_table"],
	}


def _sync_state(site: str | None, site_name: str, apartments: dict) -> dict:
	"""Compare each apartment with the projects already on the site: new, changed (and what) or in
	sync; and list the site's unit projects whose apartment is no longer in the table."""
	counts = {"new": 0, "changed": 0, "synced": 0}
	projects = {}
	if site:
		for p in frappe.get_all("Project", filters={"fk_parent_project": site},
		                        fields=["name", "project_type", "fk_house_number", "fk_unit_name", "fk_floor",
		                                "fk_unit_qty", "fk_tender_manifest", "fk_unit_configuration"]):
			projects[(cstr(p.fk_house_number).upper(), p.project_type)] = p
	labels = {"fk_unit_name": _("Unit Name"), "fk_floor": _("Floor"), "fk_unit_qty": _("Qty"),
	          "fk_tender_manifest": _("Manifest"), "fk_unit_configuration": _("Apt Type")}
	for apt in apartments.values():
		key = apt["number"].upper()
		changes, missing = [], []
		configuration = build_configuration_code(apt["type"], site_name) if apt["type"] else None
		for project_type, row in apt["rows"].items():
			p = projects.pop((key, project_type), None)
			if not p:
				missing.append(project_type)
				continue
			want = {"fk_unit_name": apt["name"] or None, "fk_floor": apt["floor"] or None, "fk_unit_qty": row["qty"],
			        "fk_tender_manifest": row["manifest"], "fk_unit_configuration": configuration}
			for field, value in want.items():
				if cstr(p.get(field) or "") != cstr(value or ""):
					changes.append(f"{_(project_type)} {labels[field]}")
		if KITCHEN_PROJECT_TYPE in missing:
			apt["sync"], apt["changes"] = "new", []
		elif missing or changes:
			apt["sync"], apt["changes"] = "changed", changes + [_("{0} to create").format(_(pt)) for pt in missing]
		else:
			apt["sync"], apt["changes"] = "synced", []
		counts[apt["sync"]] += 1
	not_in_table = sorted({p.fk_house_number for p in projects.values() if p.fk_house_number})
	return {"counts": counts, "not_in_table": not_in_table}


# ---------------------------------------------------------------- create


@frappe.whitelist()
def create_unit_projects(tender: str):
	doc = _get_won_tender(tender, "write")
	if not doc.company:
		frappe.throw(_("Set the Company on the Units tab first."))
	if not frappe.has_permission("Project", "create"):
		frappe.throw(_("You need permission to create Projects."), frappe.PermissionError)
	if doc.party_type == "Lead" and not frappe.has_permission("Customer", "create"):
		frappe.throw(_("The party is a Lead; converting it to a Customer needs permission to create Customers."), frappe.PermissionError)
	if doc.unit_import_status == "Creating":
		frappe.throw(_("The projects are already being created."))
	if preview_units(doc.name)["errors"]:
		frappe.throw(_("Fix the errors in the preview first."))

	frappe.db.set_value("Tender", doc.name, {"unit_import_status": "Creating", "unit_import_summary": ""}, update_modified=False)
	frappe.db.commit()
	frappe.enqueue(
		"fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender_units.build_unit_projects",
		queue="long",
		timeout=3600,
		tender=doc.name,
		now=frappe.flags.in_test,
	)


def build_unit_projects(tender: str):
	"""Background job: create (or update) the site, apartment types and apartment projects."""
	doc = frappe.get_doc("Tender", tender)
	stats = {"configurations": 0, "manifests": 0, "created": 0, "updated": 0}
	try:
		site_name = _site_name(doc)
		rows = [{**{k: r.get(k) for k in UNIT_FIELDS}, "_row": r.idx} for r in doc.get("unit_types") or []]
		plan = _plan(doc, rows, site_name, where=_where_apartment)
		if plan["errors"]:
			raise frappe.ValidationError("\n".join(plan["errors"]))
		customer = _party_customer(doc)
		site = _ensure_site(doc, site_name, customer)
		total, done = max(1, len(plan["apartments"])), 0

		for apt_type in plan["types"]:
			code = build_configuration_code(apt_type["code"], site_name)
			_ensure_configuration(code, apt_type["code"], site_name)
			production = {
				m["manifest"]: _upsert_production_manifest(apt_type["code"], site_name, code, m["manifest"], m["project_type"], stats)
				for m in apt_type["manifests"]
			}
			apartments = [a for a in plan["apartments"] if a["type"] == apt_type["code"]]
			# the type's configuration points at the manifests of its first apartment
			first = {r["project_type"]: r["manifest"] for r in apartments[0]["rows"]}
			slots = {CONFIGURATION_SLOT[pt]: production[m] for pt, m in first.items() if pt in CONFIGURATION_SLOT}
			frappe.db.set_value("Project Unit Configuration", code, {"tender_manifest": first.get(KITCHEN_PROJECT_TYPE), **slots})
			stats["configurations"] += 1

			for apt in apartments:
				rows_by_type = {r["project_type"]: r for r in apt["rows"]}
				kitchen = _upsert_unit(doc, site, site_name, customer, code, apt, rows_by_type[KITCHEN_PROJECT_TYPE], None, production, stats)
				for project_type, row in rows_by_type.items():
					if project_type != KITCHEN_PROJECT_TYPE:
						_upsert_unit(doc, site, site_name, customer, code, apt, row, kitchen, production, stats)
				done += 1
				if done % 10 == 0 or done == total:
					frappe.publish_progress(done * 100 / total, title=_("Creating unit projects"), doctype="Tender", docname=doc.name,
					                        description=_("{0} of {1} apartments").format(done, total))
			frappe.db.commit()

		summary = _(
			"Site {0}: {1} unit projects created, {2} updated; {3} apartment types and {4} manifests set up."
		).format(site, stats["created"], stats["updated"], stats["configurations"], stats["manifests"])
		frappe.db.set_value("Tender", doc.name, {"unit_import_status": "Completed", "unit_import_summary": summary, "project": site}, update_modified=False)
		frappe.db.commit()
		frappe.publish_realtime("tender_units_done", {"tender": doc.name, "ok": True, "site": site, "summary": summary}, user=frappe.session.user)
	except Exception:
		frappe.db.rollback()
		frappe.db.set_value("Tender", tender, {"unit_import_status": "Failed", "unit_import_summary": frappe.get_traceback()[-4000:]}, update_modified=False)
		frappe.db.commit()
		frappe.publish_realtime("tender_units_done", {"tender": tender, "ok": False}, user=frappe.session.user)
		raise


def _party_customer(doc) -> str:
	"""The tender's Customer, converting its Lead (ERPNext's own Lead -> Customer) if need be."""
	if doc.party_type == "Customer":
		return doc.party_name
	lead = doc.party_name
	customer = frappe.db.get_value("Customer", {"lead_name": lead}, "name")
	if not customer:
		from erpnext.crm.doctype.lead.lead import make_customer

		new = make_customer(lead)
		new.insert()
		customer = new.name
	title = frappe.db.get_value("Customer", customer, "customer_name") or customer
	frappe.db.set_value("Tender", doc.name, {"party_type": "Customer", "party_name": customer, "party_title": title}, update_modified=False)
	# the lead's own tender templates follow it
	for name in frappe.get_all("Tender Configuration Template", filters={"party_type": "Lead", "party_name": lead}, pluck="name"):
		frappe.db.set_value("Tender Configuration Template", name, {"party_type": "Customer", "party_name": customer, "party_title": title}, update_modified=False)
	doc.party_type, doc.party_name = "Customer", customer
	return customer


def _ensure_site(doc, site_name: str, customer: str) -> str:
	site = frappe.db.get_value("Project", {"project_type": SITE_PROJECT_TYPE, "project_name": site_name}, "name")
	values = {"customer": customer, "fk_developer": customer, "fk_tender": doc.name}
	if site:
		frappe.db.set_value("Project", site, values)
		return site
	project = frappe.get_doc({"doctype": "Project", "project_name": site_name, "project_type": SITE_PROJECT_TYPE,
	                         "company": doc.company, "status": "Open", **values})
	project.insert()
	return project.name


def _ensure_configuration(code: str, apt_type: str, site_name: str):
	if not frappe.db.exists("Project Unit Configuration", code):
		frappe.get_doc({"doctype": "Project Unit Configuration", "configuration_code": code,
		                "configuration_name": build_configuration_display_name(apt_type, site_name),
		                "scope": "Project Template"}).insert(ignore_permissions=True)


def _upsert_production_manifest(apt_type, site_name, configuration, tender_manifest, project_type, stats) -> str:
	"""A Project Template manifest for one apartment type, built from a tender manifest's item rows."""
	code = f"{apt_type.strip()}-{tender_manifest}-{normalize_site_scope(site_name)}"
	category = MANIFEST_CATEGORY.get(project_type, "Unit")
	items = []
	for line in _manifest_rows(frappe.get_doc("Tender Manifest", tender_manifest)):
		bom = resolve_manifest_linked_bom(line["item_code"])
		items.append({
			"item_code": line["item_code"],
			"description": line["item_name"],
			"qty": line["qty"],
			"uom": line["uom_code"],
			"room": "Appliances" if "APPLIANCE" in (line["section"] or "").upper() else category,
			"linked_bom": bom,
			"label_category": resolve_label_category(line["item_code"], bom),
			"notes": line["specification"] or None,
		})
	if frappe.db.exists("Manifest", code):
		manifest = frappe.get_doc("Manifest", code)
		manifest.set("items", items)
		manifest.update({"manifest_category": category, "configuration": configuration})
	else:
		manifest = frappe.get_doc({"doctype": "Manifest", "manifest_code": code, "scope": "Project Template",
		                           "manifest_category": category, "configuration": configuration, "items": items})
	manifest.flags.ignore_permissions = True
	manifest.save()
	stats["manifests"] += 1
	return manifest.name


def _upsert_unit(doc, site, site_name, customer, configuration, apt, row, parent_unit, production, stats) -> str:
	project_type = row["project_type"]
	values = {
		"project_name": build_unit_project_name(site_name, apt["number"], project_type),
		"project_type": project_type,
		"fk_parent_project": site,
		"fk_house_number": apt["number"],
		"fk_unit_name": apt["name"] or None,
		"fk_floor": apt["floor"] or None,
		"fk_unit_qty": row["qty"],
		"fk_parent_unit_project": parent_unit,
		"fk_unit_configuration": configuration,
		"fk_tender_manifest": row["manifest"],
		"company": doc.company,
		"customer": customer,
		"fk_developer": customer,
	}
	effective = production[row["manifest"]]
	existing = frappe.db.get_value("Project", {"fk_parent_project": site, "fk_house_number": apt["number"], "project_type": project_type}, "name")
	if existing:
		# a manifest amended for this one unit (Unit Snapshot) is kept
		current = frappe.db.get_value("Project", existing, "fk_effective_manifest")
		if not (current and frappe.db.get_value("Manifest", current, "scope") == "Unit Snapshot"):
			values["fk_effective_manifest"] = effective
		frappe.db.set_value("Project", existing, values)
		_apply_template_if_no_tasks(existing, doc.project_template)
		stats["updated"] += 1
		return existing
	project = frappe.get_doc({"doctype": "Project", "status": "Open", "fk_effective_manifest": effective, **values,
	                         **({"project_template": doc.project_template} if doc.project_template else {})})
	project.insert()
	stats["created"] += 1
	return project.name


def _apply_template_if_no_tasks(project: str, template: str | None):
	if not template or frappe.db.exists("Task", {"project": project}):
		return
	if frappe.db.get_value("Project", project, "project_template") not in (None, "", template):
		return
	# project_template is set-only-once on the form; set it, then save to copy the tasks
	frappe.db.set_value("Project", project, "project_template", template, update_modified=False)
	frappe.get_doc("Project", project).save()


# ---------------------------------------------------------------- shared


def _get_won_tender(tender: str, ptype: str):
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission(ptype)
	if doc.status != "Won":
		frappe.throw(_("Units are set up once the tender is Won."))
	return doc


def _site_name(doc) -> str:
	return (doc.unit_site_name or doc.tender_name or "").strip()


def _tender_manifests(tender: str) -> list:
	"""The tender's manifests, kitchens first."""
	manifests = frappe.get_all("Tender Manifest", filters={"tender": tender}, fields=["name", "tender_name", "project_type"], order_by="name")
	return sorted(manifests, key=lambda m: (m.project_type not in (None, "", KITCHEN_PROJECT_TYPE), m.name))


def _manifest_label(m) -> str:
	return f"{m.name} · {m.tender_name}" if m.tender_name else m.name


def _manifest_rows(manifest) -> list[dict]:
	"""A tender manifest's item rows with a quantity, in builder order."""
	rows = [r for r in json.loads(manifest.config_rows_json or "[]") if r.get("item_code") and flt(r.get("qty")) > 0]
	items = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", [r["item_code"] for r in rows] or [""]]},
	                                          fields=["name", "item_name", "stock_uom"])}
	out = []
	for r in rows:
		item = items.get(r["item_code"])
		if not item:
			continue
		uom = r.get("uom") or item.stock_uom
		out.append({
			"section": (r.get("section") or "").title(),
			"label": r.get("label"),
			"item_code": r["item_code"],
			"item_name": item.item_name,
			"qty": flt(r.get("qty")),
			"uom": uom,
			"uom_code": uom if frappe.db.exists("UOM", uom) else item.stock_uom,
			"specification": (r.get("specification") or "").strip(),
		})
	return out


def _rows(ws, wanted: list[str], header_row: int = 1, columns: int | None = None):
	"""(row number, {header: value}) for the non-blank data rows under header_row, by header name;
	only the first `columns` columns are read (the rest of the sheet can hold other things)."""
	headers = [cstr(c.value).strip() for c in next(ws.iter_rows(min_row=header_row, max_row=header_row, max_col=columns))]
	index = {h: i for i, h in enumerate(headers)}
	for n, values in enumerate(ws.iter_rows(min_row=header_row + 1, max_col=columns, values_only=True), start=header_row + 1):
		if not any(v not in (None, "") for v in values):
			continue
		yield n, {h: (values[index[h]] if h in index and index[h] < len(values) else None) for h in wanted}


def _text(value) -> str:
	"""A cell as text; whole-number floats (101.0) as 101."""
	if isinstance(value, float) and value == int(value):
		return str(int(value))
	return cstr(value).strip()


def _whole_number(value, default):
	"""int for whole numbers (blank -> default), None when it isn't one."""
	if value in (None, ""):
		return default
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	if number < 0 or number != int(number):
		return None
	return int(number)


def _sheet_name(number: int, title: str, taken: list[str]) -> str:
	base = re.sub(r"[\[\]:*?/\\]", "-", f"{number}. {title}").strip()[:31].rstrip()
	name, n = base, 2
	while name in taken:
		suffix = f" ({n})"
		name, n = base[: 31 - len(suffix)] + suffix, n + 1
	return name
