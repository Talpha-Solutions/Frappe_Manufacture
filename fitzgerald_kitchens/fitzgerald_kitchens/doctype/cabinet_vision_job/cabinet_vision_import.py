# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Import a Cabinet Vision report database (exported to JSON by export_cabinet_vision.ps1) into a Cabinet Vision Job.

The export holds every table of the report database, keyed by table name, with Cabinet Vision's own column
names. From it the job gets its header, rooms, moldings and material totals; each cabinet becomes a
Cabinet Vision Cabinet with its parts, doors, drawers / roll-outs and accessories; and every material the
job uses becomes (or updates) a shared Cabinet Vision Material. CV works in inches: sizes are kept as CV
had them and in mm, areas in m².

Importing again replaces the job's rooms, cabinets and totals with the file's, so a re-exported job can be
brought up to date. Materials keep their ERPNext Item, and cabinets that already have a BOM are kept.
"""

import json
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime

EXPORT_FORMAT = "cabinet-vision-report"
MM_PER_INCH = 25.4
M2_PER_SQ_INCH = 0.00064516

CABINET_TYPES = {1: "Base", 2: "Wall", 3: "Tall"}
# CxMaterial.MaterialTypeID: CV doesn't name them in the report database, these are what they hold
MATERIAL_TYPES = {
	1: "Sheet",
	2: "Door & Solid Stock",
	4: "Edge Banding",
	5: "Hinge",
	6: "Runner",
	8: "Placeholder",
	14: "Hinge Plate",
}
HARDWARE_TYPES = {"Hinge", "Hinge Plate", "Runner"}
# CxUnitOfIssue
UNITS_OF_ISSUE = {
	1: "Each",
	2: "Per FT",
	3: "SQ FT",
	4: "BD FT",
	5: "Sheet",
	6: "Per M",
	7: "SQ M",
	8: "BD M",
	9: "Cubic M",
	10: "Cubic FT",
	11: "Pair",
}
CV_BLANK_DATE_YEAR = 1899  # CV writes 1899-12-30 for "no date"


def import_job(job: str) -> dict:
	"""Read the job's attached export and (re)build its records. Returns the counts for the summary."""
	doc = frappe.get_doc("Cabinet Vision Job", job)
	doc.check_permission("write")
	if not doc.export_file:
		frappe.throw(_("Attach the Cabinet Vision export file first."))

	tables = read_export(doc.export_file)
	try:
		counts = _import(doc, tables)
	except Exception:
		frappe.db.rollback()
		frappe.db.set_value("Cabinet Vision Job", job, {"import_status": "Failed", "imported_on": now_datetime()})
		frappe.db.commit()
		raise
	return counts


def read_export(file_url: str) -> dict:
	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	if isinstance(content, bytes):
		content = content.decode("utf-16") if content[:2] in (b"\xff\xfe", b"\xfe\xff") else content.decode("utf-8-sig")
	try:
		data = json.loads(content.strip())
	except ValueError:
		frappe.throw(_("The export file isn't valid JSON. Export the job again with export_cabinet_vision.ps1."))
	if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
		frappe.throw(_("This isn't a Cabinet Vision export: make it with export_cabinet_vision.ps1."))
	tables = data.get("tables") or {}
	missing = [t for t in ("Job Info", "Cabinets", "Parts") if t not in tables]
	if missing:
		frappe.throw(_("The export has no {0} table: is it a Cabinet Vision report database?").format(", ".join(missing)))
	tables["_database"] = data.get("database")
	return tables


# ------------------------------------------------------------------------------------------- import


def _import(doc, tables: dict) -> dict:
	job_info = (tables.get("Job Info") or [{}])[0]
	db_info = (tables.get("DB Info") or [{}])[0]

	materials = _import_materials(tables)  # {CV material ID: Cabinet Vision Material name}

	doc.job_name = job_info.get("Job Name") or tables.get("_database")
	doc.job_number = job_info.get("Job Number")
	doc.designer = job_info.get("Key Name")
	doc.cv_customer_name = job_info.get("Customer Name")
	doc.cvj_file = job_info.get("CVJFile")
	doc.cv_version = str(db_info.get("Version") or "")
	doc.cv_guid = db_info.get("rGUID")
	doc.measure_date = _date(job_info.get("Measure"))
	doc.production_date = _date(job_info.get("Production"))
	doc.delivery_date = _date(job_info.get("Delivery"))
	doc.install_date = _date(job_info.get("Install"))

	rooms = tables.get("Rooms") or []
	room_names = {}
	for r in rooms:
		for key in ("RoomNumber", "RoomID"):  # cabinets point at RoomNumber; older files may use RoomID
			if r.get(key) is not None:
				room_names.setdefault(cint(r[key]), r.get("RoomName"))

	doc.set("rooms", [_room(r) for r in rooms])
	doc.set("moldings", [_molding(m, room_names, materials) for m in tables.get("Molding") or []])

	cabinets, parts_by_cabinet = _build_cabinets(doc.name, tables, room_names, materials)
	kept_with_bom = _save_cabinets(doc.name, cabinets)

	doc.set("cabinets", [_job_cabinet(doc.name, c) for c in cabinets])
	doc.set("materials", _job_materials(tables, parts_by_cabinet, materials))
	doc.cabinet_count = len(cabinets)
	doc.part_count = sum(len(c["parts"]) for c in cabinets)
	doc.import_status = "Imported"
	doc.imported_on = now_datetime()

	unlinked = sum(1 for c in cabinets for p in c["parts"] if p["cv_material_id"] and not p["material"])
	by_others = sum(1 for c in cabinets if c["by_others"])
	summary = [
		_("{0} room(s), {1} cabinet(s), {2} part(s), {3} material(s) from {4}.").format(
			len(rooms), len(cabinets), doc.part_count, len(doc.materials), tables.get("_database") or _("the export")
		)
	]
	if by_others:
		summary.append(_("{0} item(s) supplied by others.").format(by_others))
	if unlinked:
		summary.append(_("{0} part(s) use a material that isn't in the export's material library.").format(unlinked))
	if kept_with_bom:
		summary.append(
			_("Kept {0} cabinet(s) no longer in the file because they have a BOM: {1}").format(
				len(kept_with_bom), ", ".join(kept_with_bom)
			)
		)
	doc.import_summary = "\n".join(summary)
	doc.save()

	return {"cabinets": len(cabinets), "parts": doc.part_count, "materials": len(doc.materials), "summary": doc.import_summary}


# ---------------------------------------------------------------------------------------- materials


def _used_material_ids(tables: dict) -> set:
	ids = set()
	for row in tables.get("Parts") or []:
		ids.add(cint(row.get("Material ID")))
	for row in tables.get("Doors") or []:
		ids.add(cint(row.get("HingeMatID")))
	for row in (tables.get("Drawers") or []) + (tables.get("Rollouts") or []):
		ids.add(cint(row.get("GuideMaterialID")))
	for row in tables.get("Molding") or []:
		ids.add(cint(row.get("Material ID")))
	return {i for i in ids if i > 0}


def _import_materials(tables: dict) -> dict:
	"""Create or update a Cabinet Vision Material for each material the job uses. {CV ID: record name}"""
	used = _used_material_ids(tables)
	library = {cint(m.get("ID")): m for m in tables.get("CxMaterial") or [] if cint(m.get("ID")) in used}
	thickness = {cint(b.get("MaterialID")): flt(b.get("Thickness")) for b in tables.get("CxMaterialExtraBoardInfo") or []}
	sizes = {cint(s.get("MaterialID")): s for s in tables.get("CxMaterialExtraSizeInfo") or []}

	out = {}
	for cv_id, m in library.items():
		name = (m.get("Name") or "").strip() or _("CV material {0}").format(cv_id)
		guid = (m.get("rGUID") or "").strip() or None
		existing = (guid and frappe.db.get_value("Cabinet Vision Material", {"cv_guid": guid})) or frappe.db.get_value(
			"Cabinet Vision Material", {"material_name": name, "cv_material_id": cv_id}
		)
		mat = frappe.get_doc("Cabinet Vision Material", existing) if existing else frappe.new_doc("Cabinet Vision Material")
		size = sizes.get(cv_id) or {}
		type_id = cint(m.get("MaterialTypeID"))
		mat.update(
			{
				"material_name": name,
				"description": m.get("Description"),
				"material_type": MATERIAL_TYPES.get(type_id, "Other"),
				"unit_of_issue": UNITS_OF_ISSUE.get(cint(m.get("UnitOfIssueID"))),
				"cv_material_id": cv_id,
				"cv_material_type_id": type_id,
				"cv_guid": guid,
				"thickness_mm": thickness.get(cv_id) or flt(size.get("Thickness")),
				"sheet_width_mm": flt(size.get("Width")),
				"sheet_length_mm": flt(size.get("Length")),
				"cv_default_cost": flt(m.get("DefaultCost")),
				"waste_pct": flt(m.get("Waste")),
			}
		)
		mat.flags.ignore_permissions = True  # the job's write permission was checked; materials are shared
		mat.save()
		out[cv_id] = mat.name
	return out


def _material_info(names: set) -> dict:
	if not names:
		return {}
	return {
		m.name: m
		for m in frappe.get_all(
			"Cabinet Vision Material",
			filters={"name": ["in", list(names)]},
			fields=["name", "material_type", "waste_pct", "cv_material_id"],
		)
	}


def _job_materials(tables: dict, parts_by_cabinet: dict, materials: dict) -> list[dict]:
	"""The job's take-off per material: parts, sheet area, banding / molding length, hardware count."""
	info = _material_info(set(materials.values()))
	overrides = {cint(o.get("MatID")): flt(o.get("Waste")) for o in tables.get("MaterialOverride") or []}
	totals = defaultdict(lambda: {"part_count": 0, "area_m2": 0.0, "length_m": 0.0, "qty": 0.0})

	for parts in parts_by_cabinet.values():
		for p in parts:
			if not p["material"]:
				continue
			t = totals[p["material"]]
			t["part_count"] += 1
			if p["is_hardware"]:
				t["qty"] += 1
			elif info[p["material"]].material_type == "Edge Banding":
				t["length_m"] += p["length_mm"] / 1000
			else:
				t["area_m2"] += p["area_m2"]
	for m in tables.get("Molding") or []:
		name = materials.get(cint(m.get("Material ID")))
		if name:
			totals[name]["length_m"] += flt(m.get("Lineal Total")) * MM_PER_INCH / 1000

	rows = []
	for name, t in totals.items():
		mat = info[name]
		cv_id = cint(mat.cv_material_id)
		rows.append(
			{
				"material": name,
				"part_count": t["part_count"],
				"area_m2": round(t["area_m2"], 4),
				"length_m": round(t["length_m"], 3),
				"qty": t["qty"],
				"waste_pct": overrides[cv_id] if cv_id in overrides else flt(mat.waste_pct),
			}
		)
	rows.sort(key=lambda r: (-r["area_m2"], -r["length_m"], -r["qty"]))
	return rows


# ----------------------------------------------------------------------------------------- cabinets


def _build_cabinets(job: str, tables: dict, room_names: dict, materials: dict):
	info = _material_info(set(materials.values()))
	by_cabinet = defaultdict(lambda: defaultdict(list))
	for p in tables.get("Parts") or []:
		by_cabinet[cint(p.get("Cabinet ID"))]["parts"].append(p)
	for d in tables.get("Doors") or []:
		by_cabinet[cint(d.get("Cabinet ID"))]["doors"].append(d)
	for d in tables.get("Drawers") or []:
		by_cabinet[cint(d.get("Cabinet ID"))]["drawers"].append(("Drawer", d))
	for d in tables.get("Rollouts") or []:
		by_cabinet[cint(d.get("Cabinet ID"))]["drawers"].append(("Roll-out", d))
	for a in tables.get("Accessories") or []:
		by_cabinet[cint(a.get("ACabinet ID"))]["accessories"].append(a)

	cabinets, parts_by_cabinet = [], {}
	# the export doesn't keep CV's row order, so go by cabinet ID (the order they were drawn in)
	for c in sorted(tables.get("Cabinets") or [], key=lambda c: cint(c.get("Cabinet ID"))):
		cv_id = cint(c.get("Cabinet ID"))
		children = by_cabinet.get(cv_id, {})
		name, description = (c.get("Cabinet Name") or "").strip(), (c.get("Description") or "").strip()
		parts = [_part(p, materials, info) for p in children.get("parts", [])]
		parts_by_cabinet[cv_id] = parts
		cabinets.append(
			{
				"job": job,
				"cv_cabinet_id": cv_id,
				"cabinet_name": name,
				"description": description,
				"room": room_names.get(cint(c.get("Room ID"))),
				"wall_id": cint(c.get("Wall ID")),
				"cabinet_type": CABINET_TYPES.get(cint(c.get("Cabinet Type")), "Other"),
				"category": _category(name, description),
				"by_others": 1 if "BY OTHERS" in f"{name} {description}".upper() else 0,
				"catalog": c.get("Catalog"),
				"qty": cint(c.get("Quantity")) or 1,
				"openings": cint(c.get("Openings")),
				**_size(c, "Width", "Height", "Depth"),
				"left_end": c.get("Left End"),
				"right_end": c.get("Right End"),
				"back": c.get("Back"),
				"hinge": c.get("Hinge"),
				"toe_height_in": flt(c.get("Toe Height")),
				"toe_recess_in": flt(c.get("Toe Recess")),
				"elevation_in": flt(c.get("Elevation")),
				"finished_area": flt(c.get("Finished Area")),
				"cvc_asm_id": cint(c.get("CvcAsmID")),
				"assembly_params": c.get("Assembly"),
				"parts": parts,
				"doors": [_door(d, materials) for d in children.get("doors", [])],
				"drawers": [_drawer(kind, d, materials) for kind, d in children.get("drawers", [])],
				"accessories": [_accessory(a) for a in children.get("accessories", [])],
			}
		)
		cab = cabinets[-1]
		cab.update(part_count=len(cab["parts"]), door_count=len(cab["doors"]), drawer_count=len(cab["drawers"]))
	return cabinets, parts_by_cabinet


def _save_cabinets(job: str, cabinets: list[dict]) -> list[str]:
	"""Upsert the cabinets; delete the job's cabinets that aren't in the file, unless they have a BOM."""
	keep = set()
	for data in cabinets:
		name = f"{job}-{data['cv_cabinet_id']}"
		if frappe.db.exists("Cabinet Vision Cabinet", name):
			cab = frappe.get_doc("Cabinet Vision Cabinet", name)
			for table in ("parts", "doors", "drawers", "accessories"):
				cab.set(table, [])
		else:
			cab = frappe.new_doc("Cabinet Vision Cabinet")
		cab.update(data)
		cab.flags.ignore_permissions = True  # the job's write permission was checked
		cab.save()
		keep.add(cab.name)

	kept_with_bom = []
	for old in frappe.get_all("Cabinet Vision Cabinet", filters={"job": job}, fields=["name", "bom"]):
		if old.name in keep:
			continue
		if old.bom:
			kept_with_bom.append(old.name)
		else:
			frappe.delete_doc("Cabinet Vision Cabinet", old.name, ignore_permissions=True)
	return kept_with_bom


def _job_cabinet(job: str, c: dict) -> dict:
	"""The job's overview row for a cabinet, linking to its full record."""
	return {
		"cabinet": f"{job}-{c['cv_cabinet_id']}",
		"cabinet_name": c["cabinet_name"],
		"cabinet_type": c["cabinet_type"],
		"category": c["category"],
		"width_mm": c["width_mm"],
		"height_mm": c["height_mm"],
		"depth_mm": c["depth_mm"],
		"part_count": c["part_count"],
		"room": c["room"],
		"by_others": c["by_others"],
	}


def _category(name: str, description: str) -> str:
	upper_name, text = name.upper(), f"{name} {description}".upper()
	if upper_name.startswith("TOE"):
		return "Toe Kick"
	if "FILLER" in text or re.search(r"\.(L|R)F\b", upper_name):
		return "Filler"
	if upper_name.startswith("CT") or re.search(r"\b(COUNTER ?TOP|WORK ?TOP)\b", text):
		return "Worktop"
	if re.search(r"\.FS\b", upper_name) or "FLOATING SHELF" in text:
		return "Shelf"
	return "Cabinet"


# ------------------------------------------------------------------------------------- child rows


def _size(row: dict, *keys: str) -> dict:
	out = {}
	for key in keys:
		value = flt(row.get(key))
		out[f"{key.lower()}_in"] = value
		out[f"{key.lower()}_mm"] = round(value * MM_PER_INCH, 2)
	return out


def _part(p: dict, materials: dict, info: dict) -> dict:
	cv_material_id = cint(p.get("Material ID"))
	material = materials.get(cv_material_id)
	material_type = info[material].material_type if material else None
	area_in2 = flt(p.get("Area")) or flt(p.get("Width")) * flt(p.get("Length"))
	return {
		"description": p.get("Description"),
		"material": material,
		"cv_material_id": cv_material_id if cv_material_id > 0 else None,
		**_size(p, "Width", "Length"),
		"area_m2": round(area_in2 * M2_PER_SQ_INCH, 6),
		"edge_band": p.get("EdgeBand"),
		"banding": p.get("Banding"),
		"is_hardware": 1 if (material_type in HARDWARE_TYPES or (material and not area_in2)) else 0,
		"barcode": p.get("BarCode"),
		"buy_out": 1 if cint(p.get("BuyOut")) else 0,
		"cv_part_id": cint(p.get("ID")),
		"door_id": cint(p.get("Door ID")),
		"drawer_id": cint(p.get("Drawer ID")),
		"rollout_id": cint(p.get("RollOut ID")),
		"face_finish": _text(p.get("FaceFinishID")),
		"back_finish": _text(p.get("BackFinishID")),
		"edge_finish": _text(p.get("EdgeFinishID")),
		"num_drill": cint(p.get("NumDrill")),
		"num_route": cint(p.get("NumRoute")),
		"num_dado": cint(p.get("NumDado")),
	}


def _door(d: dict, materials: dict) -> dict:
	return {
		"door_name": d.get("Door Name"),
		"door_type": d.get("Type"),
		"hinge_side": d.get("Hinge"),
		**_size(d, "Width", "Height"),
		"material_schedule": d.get("Material Schedule"),
		"edge_profile": d.get("Edge Profile"),
		"panel_detail": d.get("Raised Panel Detail"),
		"pulls": cint(d.get("Pulls")),
		"hinges": cint(d.get("Hinges")),
		"hinge_material": materials.get(cint(d.get("HingeMatID"))),
		"end_panel": 1 if cint(d.get("EndPanel")) else 0,
		"cv_door_id": cint(d.get("Door ID")),
	}


def _drawer(kind: str, d: dict, materials: dict) -> dict:
	return {
		"kind": kind,
		"drawer_name": d.get("Drawer Name") or d.get("Rollout Name"),
		**_size(d, "Width", "Height", "Depth"),
		"material_schedule": d.get("MaterialSchedule"),
		"guide_material": materials.get(cint(d.get("GuideMaterialID"))),
		"guide_location": d.get("Guide Location"),
		"cv_drawer_id": cint(d.get("Drawer ID") or d.get("Rollout ID")),
	}


def _accessory(a: dict) -> dict:
	return {
		"accessory": a.get("Access"),
		"qty": flt(a.get("AQuantity")) or 1,
		"description": a.get("ADescription"),
		"catalog": a.get("ACatalog Name"),
		"width_in": flt(a.get("AWidth")),
		"height_in": flt(a.get("AHeight")),
		"depth_in": flt(a.get("ADepth")),
		"cv_accessory_id": cint(a.get("Access ID")),
	}


def _room(r: dict) -> dict:
	return {
		"room_name": r.get("RoomName"),
		"room_number": cint(r.get("RoomNumber")),
		"cv_room_id": cint(r.get("RoomID")),
		"room_description": r.get("RoomDescription"),
		"qty": cint(r.get("Quantity")) or 1,
		"construction": r.get("CabinetConstruction"),
		"exterior_finish": r.get("ExtAsmFin"),
		"interior_finish": r.get("IntAsmFin"),
		"base_cabinet_material": r.get("BaseCabinetMaterials"),
		"base_exposed_material": r.get("BaseExposedCabinetMaterials"),
		"wall_cabinet_material": r.get("WallCabinetMaterials"),
		"wall_exposed_material": r.get("WallExposedCabinetMaterials"),
		"base_end_panel_material": r.get("BaseEndPanelMaterial"),
		"wall_end_panel_material": r.get("WallEndPanelMaterial"),
		"tall_end_panel_material": r.get("TallEndPanelMaterial"),
		"base_door_name": r.get("BaseDoorName"),
		"base_door_material": r.get("BaseDoorMaterial"),
		"wall_door_name": r.get("WallDoorName"),
		"wall_door_material": r.get("WallDoorMaterial"),
		"drawer_front_name": r.get("DrawerFrontName"),
		"drawer_front_material": r.get("DrawerFrontMaterial"),
		"drawer_box_material": r.get("DrawerBoxMaterials"),
		"rollout_material": r.get("RollOutMaterials"),
		"hinge_material": r.get("HingeMaterials"),
		"guide_material": r.get("GuideMaterials"),
		"pull_material": r.get("PullMaterials"),
		"countertop_material": r.get("CounterTopMaterial"),
	}


def _molding(m: dict, room_names: dict, materials: dict) -> dict:
	lineal_in = flt(m.get("Lineal Total"))
	return {
		"room": room_names.get(cint(m.get("Room ID"))),
		"style": m.get("Style"),
		"material": materials.get(cint(m.get("Material ID"))),
		"lineal_in": round(lineal_in, 4),
		"lineal_m": round(lineal_in * MM_PER_INCH / 1000, 3),
		"miters": cint(m.get("Miter")),
		"height_in": round(flt(m.get("Height")), 5),
		"thickness_in": round(flt(m.get("Thickness")), 5),
		"profile_id": cint(m.get("ProfileID")),
		"cv_molding_id": cint(m.get("Molding ID")),
	}


def _date(value):
	if not value:
		return None
	date = getdate(str(value)[:10])
	return None if date.year <= CV_BLANK_DATE_YEAR else date


def _text(value):
	return None if value in (None, "", 0) else str(value)
