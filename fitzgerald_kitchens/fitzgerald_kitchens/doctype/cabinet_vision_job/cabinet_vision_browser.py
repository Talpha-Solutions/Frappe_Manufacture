# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""The Cabinet Vision Browser: the tree view of a job (/app/cabinet-vision-job/view/tree).

Job → Room → Base / Wall / Tall (and Plinths, Fillers, Shelves, Worktops) → Cabinet →
Parts by material / Doors & fronts / Drawers & roll-outs / Accessories → each row.

Every node's value is "<kind>::<key>[::<key>]" so values are unique across the tree, and
get_node_detail() returns what the right-hand panel shows for whichever node is clicked.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, sbool

SEP = "::"
NO_ROOM = "(No room)"
NO_MATERIAL = "(No material)"
# Cabinets group by type; everything else by category, in this order
GROUPS = ["Base", "Wall", "Tall", "Other", "Toe Kick", "Filler", "Shelf", "Worktop"]
GROUP_LABELS = {
	"Base": "Base Cabinets",
	"Wall": "Wall Cabinets",
	"Tall": "Tall Cabinets",
	"Other": "Other Cabinets",
	"Toe Kick": "Plinths",
	"Filler": "Fillers",
	"Shelf": "Shelves",
	"Worktop": "Worktops",
}
CABINET_FIELDS = [
	"name", "cabinet_name", "description", "cabinet_type", "category", "by_others", "room",
	"width_mm", "height_mm", "depth_mm", "part_count", "door_count", "drawer_count", "cv_cabinet_id",
]


def _value(*parts) -> str:
	return SEP.join(str(p) for p in parts)


def _split(value: str) -> list[str]:
	return (value or "").split(SEP)


def _check_job(job: str):
	if not job or not frappe.db.exists("Cabinet Vision Job", job):
		return False
	frappe.has_permission("Cabinet Vision Job", "read", doc=job, throw=True)
	return True


def _group_of(cabinet) -> str:
	return cabinet.cabinet_type if cabinet.category == "Cabinet" else cabinet.category


def _cabinets(job: str) -> list:
	return frappe.get_all(
		"Cabinet Vision Cabinet", filters={"job": job}, fields=CABINET_FIELDS, order_by="cv_cabinet_id"
	)


def _material_names(names) -> dict:
	names = [n for n in set(names) if n]
	if not names:
		return {}
	return {
		m.name: m
		for m in frappe.get_all(
			"Cabinet Vision Material",
			filters={"name": ["in", names]},
			fields=["name", "material_name", "material_type", "unit_of_issue", "item"],
		)
	}


def _size(row) -> str:
	dims = [flt(row.get(k)) for k in ("width_mm", "height_mm", "depth_mm") if row.get(k) is not None]
	return " × ".join(f"{d:g}" for d in (round(x) for x in dims))


# ------------------------------------------------------------------------------------------- tree


@frappe.whitelist()
def get_children(doctype=None, parent=None, is_root=False, job=None, **kwargs):
	is_root = sbool(is_root)
	job = job or (parent if is_root else None)
	if not _check_job(job):
		return []

	if is_root or parent == job:
		return _room_nodes(job)

	kind, *keys = _split(parent)
	if kind == "room":
		return _group_nodes(job, keys[0])
	if kind == "grp":
		return _cabinet_nodes(job, keys[0], keys[1])
	if kind == "cab":
		return _cabinet_section_nodes(keys[0])
	if kind == "parts":
		return _part_material_nodes(keys[0])
	if kind == "pmat":
		return _part_nodes(keys[0], keys[1])
	if kind in ("doors", "drawers", "accs"):
		return _row_nodes(kind, keys[0])
	return []


def _room_nodes(job: str) -> list[dict]:
	counts = defaultdict(int)
	for c in _cabinets(job):
		counts[c.room or NO_ROOM] += 1
	rooms = [r.room_name for r in frappe.get_all(
		"Cabinet Vision Room", filters={"parent": job, "parenttype": "Cabinet Vision Job"},
		fields=["room_name"], order_by="idx")]
	for room in counts:
		if room not in rooms:
			rooms.append(room)
	return [
		{"value": _value("room", room), "title": room, "badge": _("{0} cabinets").format(counts.get(room, 0)),
		 "kind": "room", "expandable": 1 if counts.get(room) else 0}
		for room in rooms
	]


def _group_nodes(job: str, room: str) -> list[dict]:
	counts = defaultdict(int)
	for c in _cabinets(job):
		if (c.room or NO_ROOM) == room:
			counts[_group_of(c)] += 1
	return [
		{"value": _value("grp", room, g), "title": _(GROUP_LABELS[g]), "badge": counts[g], "kind": "group", "expandable": 1}
		for g in GROUPS
		if counts.get(g)
	]


def _cabinet_nodes(job: str, room: str, group: str) -> list[dict]:
	out = []
	for c in _cabinets(job):
		if (c.room or NO_ROOM) != room or _group_of(c) != group:
			continue
		out.append(
			{
				"value": _value("cab", c.name),
				"title": c.cabinet_name or c.name,
				"badge": _size(c),
				"by_others": c.by_others,
				"kind": "cabinet",
				"cabinet": c.name,
				"expandable": 1 if (c.part_count or c.door_count or c.drawer_count) else 0,
			}
		)
	return out


def _cabinet_section_nodes(cabinet: str) -> list[dict]:
	counts = {
		table: frappe.db.count(
			f"Cabinet Vision {doctype}", {"parent": cabinet, "parenttype": "Cabinet Vision Cabinet"}
		)
		for table, doctype in (("parts", "Part"), ("doors", "Door"), ("drawers", "Drawer"), ("accs", "Accessory"))
	}
	labels = {
		"parts": _("Parts by material"),
		"doors": _("Doors & fronts"),
		"drawers": _("Drawers & roll-outs"),
		"accs": _("Accessories"),
	}
	return [
		{"value": _value(kind, cabinet), "title": labels[kind], "badge": counts[kind], "kind": kind, "cabinet": cabinet, "expandable": 1}
		for kind in ("parts", "doors", "drawers", "accs")
		if counts[kind]
	]


def _cabinet_parts(cabinet: str) -> list:
	return frappe.get_all(
		"Cabinet Vision Part",
		filters={"parent": cabinet, "parenttype": "Cabinet Vision Cabinet"},
		fields=["name", "description", "material", "width_mm", "length_mm", "area_m2", "edge_band",
		        "banding", "is_hardware", "width_in", "length_in", "barcode", "door_id", "drawer_id", "rollout_id"],
		order_by="idx",
	)


def _part_material_nodes(cabinet: str) -> list[dict]:
	parts = _cabinet_parts(cabinet)
	mats = _material_names(p.material for p in parts)
	groups = defaultdict(list)
	for p in parts:
		groups[p.material or ""].append(p)
	out = []
	for material, rows in groups.items():
		m = mats.get(material)
		out.append(
			{
				"value": _value("pmat", cabinet, material or "-"),
				"title": m.material_name if m else _(NO_MATERIAL),
				"badge": len(rows),
				"kind": "part_material",
				"cabinet": cabinet,
				"material": material,
				"expandable": 1,
			}
		)
	out.sort(key=lambda n: -n["badge"])
	return out


def _part_nodes(cabinet: str, material: str) -> list[dict]:
	material = "" if material == "-" else material
	return [
		{
			"value": _value("part", p.name),
			"title": p.description or _("Part"),
			"badge": "" if p.is_hardware else f"{round(flt(p.width_mm)):g} × {round(flt(p.length_mm)):g}",
			"kind": "part",
			"cabinet": cabinet,
			"expandable": 0,
		}
		for p in _cabinet_parts(cabinet)
		if (p.material or "") == material
	]


def _row_nodes(kind: str, cabinet: str) -> list[dict]:
	doctype, title_field, leaf = {
		"doors": ("Cabinet Vision Door", "door_name", "door"),
		"drawers": ("Cabinet Vision Drawer", "drawer_name", "drawer"),
		"accs": ("Cabinet Vision Accessory", "accessory", "accessory"),
	}[kind]
	fields = ["name", title_field, "width_mm", "height_mm"] if kind != "accs" else ["name", title_field, "qty"]
	if kind == "doors":
		fields.append("hinge_side")
	if kind == "drawers":
		fields.append("kind")
	out = []
	for r in frappe.get_all(doctype, filters={"parent": cabinet, "parenttype": "Cabinet Vision Cabinet"}, fields=fields, order_by="idx"):
		if kind == "accs":
			badge = f"× {flt(r.qty):g}"
		else:
			badge = f"{round(flt(r.width_mm)):g} × {round(flt(r.height_mm)):g}"
		title = r.get(title_field) or _("Row")
		if kind == "doors" and r.hinge_side in ("L", "R"):
			title += f" ({r.hinge_side})"
		if kind == "drawers":
			title = f"{_(r.kind)}: {title}"
		out.append({"value": _value(leaf, r.name), "title": title, "badge": badge, "kind": leaf, "cabinet": cabinet, "expandable": 0})
	return out


# ------------------------------------------------------------------------------------------- panel


@frappe.whitelist()
def get_node_detail(job: str, value: str) -> dict:
	"""What the right-hand panel shows for a node."""
	if not _check_job(job):
		return {}
	kind, *keys = _split(value)
	if value == job or kind not in ("room", "grp", "cab", "parts", "pmat", "doors", "drawers", "accs", "part", "door", "drawer", "accessory"):
		return _job_detail(job)
	if kind == "room":
		return _room_detail(job, keys[0])
	if kind == "grp":
		return _group_detail(job, keys[0], keys[1])
	if kind in ("cab", "parts", "doors", "drawers", "accs"):
		return _cabinet_detail(keys[0])
	if kind == "pmat":
		return _part_material_detail(keys[0], keys[1])
	return _row_detail(kind, keys[0])


def _job_detail(job: str) -> dict:
	doc = frappe.get_doc("Cabinet Vision Job", job)
	cabinets = _cabinets(job)
	groups = defaultdict(int)
	for c in cabinets:
		groups[_group_of(c)] += 1
	return {
		"kind": "job",
		"name": doc.name,
		"title": doc.job_name,
		"subtitle": " · ".join(x for x in (doc.job_number, doc.designer, doc.customer) if x),
		"cards": [
			{"label": _("Rooms"), "value": len(doc.rooms)},
			{"label": _("Cabinets"), "value": len(cabinets)},
			{"label": _("Parts"), "value": doc.part_count},
			{"label": _("Materials"), "value": len(doc.materials)},
		],
		"groups": [{"label": _(GROUP_LABELS[g]), "value": groups[g]} for g in GROUPS if groups.get(g)],
		"takeoff": [
			{
				"material": m.material,
				"material_name": m.material_name,
				"material_type": m.material_type,
				"part_count": m.part_count,
				"area_m2": m.area_m2,
				"length_m": m.length_m,
				"qty": m.qty,
			}
			for m in doc.materials
		],
		"moldings": [{"style": m.style, "length_m": m.lineal_m, "miters": m.miters} for m in doc.moldings],
	}


def _room_detail(job: str, room: str) -> dict:
	row = frappe.get_all(
		"Cabinet Vision Room", filters={"parent": job, "room_name": room}, fields=["*"], limit=1
	)
	row = row[0] if row else {}
	specs = [
		(_("Construction"), row.get("construction")),
		(_("Carcass"), row.get("base_cabinet_material")),
		(_("Base doors"), " / ".join(x for x in (row.get("base_door_name"), row.get("base_door_material")) if x)),
		(_("Wall doors"), " / ".join(x for x in (row.get("wall_door_name"), row.get("wall_door_material")) if x)),
		(_("Drawer fronts"), " / ".join(x for x in (row.get("drawer_front_name"), row.get("drawer_front_material")) if x)),
		(_("Drawer boxes"), row.get("drawer_box_material")),
		(_("Hinges"), row.get("hinge_material")),
		(_("Runners"), row.get("guide_material")),
		(_("Pulls"), row.get("pull_material")),
		(_("Worktop"), row.get("countertop_material")),
	]
	cabinets = [c for c in _cabinets(job) if (c.room or NO_ROOM) == room]
	return {
		"kind": "room",
		"title": room,
		"subtitle": _("{0} cabinets").format(len(cabinets)),
		"specs": [{"label": k, "value": v} for k, v in specs if v and v != "None"],
		"cabinets": [_cabinet_row(c) for c in cabinets],
	}


def _group_detail(job: str, room: str, group: str) -> dict:
	cabinets = [c for c in _cabinets(job) if (c.room or NO_ROOM) == room and _group_of(c) == group]
	return {
		"kind": "group",
		"title": _(GROUP_LABELS.get(group, group)),
		"subtitle": room,
		"cabinets": [_cabinet_row(c) for c in cabinets],
	}


def _cabinet_row(c) -> dict:
	return {
		"name": c.name,
		"cabinet_name": c.cabinet_name,
		"size": _size(c),
		"part_count": c.part_count,
		"by_others": c.by_others,
	}


def _takeoff(parts) -> list[dict]:
	mats = _material_names(p.material for p in parts)
	totals = defaultdict(lambda: {"part_count": 0, "area_m2": 0.0, "length_m": 0.0, "qty": 0})
	for p in parts:
		t = totals[p.material or ""]
		t["part_count"] += 1
		m = mats.get(p.material)
		if p.is_hardware:
			t["qty"] += 1
		elif m and m.material_type == "Edge Banding":
			t["length_m"] += flt(p.length_mm) / 1000
		else:
			t["area_m2"] += flt(p.area_m2)
	out = []
	for material, t in totals.items():
		m = mats.get(material)
		out.append(
			{
				"material": material,
				"material_name": m.material_name if m else _(NO_MATERIAL),
				"material_type": m.material_type if m else "",
				"part_count": t["part_count"],
				"area_m2": round(t["area_m2"], 3),
				"length_m": round(t["length_m"], 2),
				"qty": t["qty"],
			}
		)
	out.sort(key=lambda r: (-r["area_m2"], -r["length_m"], -r["qty"]))
	return out


def _cabinet_detail(cabinet: str) -> dict:
	cab = frappe.get_doc("Cabinet Vision Cabinet", cabinet)
	return {
		"kind": "cabinet",
		"name": cab.name,
		"title": cab.cabinet_name,
		"subtitle": " · ".join(x for x in (cab.cabinet_type, cab.category, cab.room, cab.description) if x),
		"by_others": cab.by_others,
		"width_mm": cab.width_mm,
		"height_mm": cab.height_mm,
		"depth_mm": cab.depth_mm,
		"specs": [
			{"label": _("Size (W × H × D)"), "value": f"{_size(cab)} mm"},
			{"label": _("Left end"), "value": cab.left_end},
			{"label": _("Right end"), "value": cab.right_end},
			{"label": _("Back"), "value": cab.back},
			{"label": _("Height off floor"), "value": f"{round(flt(cab.elevation_in) * 25.4):g} mm" if cab.elevation_in else None},
			{"label": _("Item"), "value": cab.item},
			{"label": _("BOM"), "value": cab.bom},
		],
		"cards": [
			{"label": _("Parts"), "value": len(cab.parts)},
			{"label": _("Doors & fronts"), "value": len(cab.doors)},
			{"label": _("Drawers & roll-outs"), "value": len(cab.drawers)},
			{"label": _("Accessories"), "value": len(cab.accessories)},
		],
		"drawers": [{"kind": d.kind, "name": d.drawer_name, "size": _size(d)} for d in cab.drawers],
		"accessories": [{"name": a.accessory, "qty": a.qty} for a in cab.accessories],
		"takeoff": _takeoff(cab.parts),
	}


def _part_material_detail(cabinet: str, material: str) -> dict:
	material = "" if material == "-" else material
	parts = [p for p in _cabinet_parts(cabinet) if (p.material or "") == material]
	m = _material_names([material]).get(material)
	return {
		"kind": "part_material",
		"title": m.material_name if m else _(NO_MATERIAL),
		"subtitle": " · ".join(x for x in (m.material_type if m else None, frappe.db.get_value("Cabinet Vision Cabinet", cabinet, "cabinet_name")) if x),
		"material": material,
		"item": m.item if m else None,
		"takeoff": _takeoff(parts),
		"parts": [
			{"description": p.description, "w": flt(p.width_mm), "l": flt(p.length_mm), "area_m2": flt(p.area_m2),
			 "edge_band": p.edge_band, "is_hardware": p.is_hardware}
			for p in parts
		],
	}


def _row_detail(kind: str, rowname: str) -> dict:
	doctype = {
		"part": "Cabinet Vision Part",
		"door": "Cabinet Vision Door",
		"drawer": "Cabinet Vision Drawer",
		"accessory": "Cabinet Vision Accessory",
	}.get(kind)
	if not doctype:
		return {}
	row = frappe.get_doc(doctype, rowname)
	meta = frappe.get_meta(doctype)
	specs = []
	for df in meta.fields:
		if df.fieldtype in ("Section Break", "Column Break", "Tab Break"):
			continue
		value = row.get(df.fieldname)
		if value in (None, "", 0) and df.fieldtype != "Check":
			continue
		if df.fieldtype == "Check":
			if not value:
				continue
			value = _("Yes")
		elif df.fieldtype == "Link" and df.options == "Cabinet Vision Material":
			value = frappe.db.get_value("Cabinet Vision Material", value, "material_name") or value
		elif df.fieldtype == "Float":
			value = f"{flt(value, cint(df.precision) or 3):g}"
		specs.append({"label": _(df.label), "value": value})
	title = row.get("description") or row.get("door_name") or row.get("drawer_name") or row.get("accessory")
	return {
		"kind": kind,
		"title": title,
		"subtitle": frappe.db.get_value("Cabinet Vision Cabinet", row.parent, "cabinet_name"),
		"cabinet": row.parent,
		"specs": specs,
	}
