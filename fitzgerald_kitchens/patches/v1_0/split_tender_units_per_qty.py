import frappe
from frappe.utils import cint

from fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender_units import link_unit_projects
from fitzgerald_kitchens.setup.project_unit_fields import KITCHEN_PROJECT_TYPE


def execute():
	"""Tender Unit Type went from a row per apartment per manifest with a Qty to a row per unit (Robe Qty
	2 is two Robe rows, No. 1 and 2), each linked to its project. Split the rows, then link them to the
	projects already on the tender's site; units without one get theirs on the next Sync Projects.

	Runs after model sync: the old qty column is no longer in the doctype but is still in the table
	(Frappe doesn't drop columns), so it's read with SQL.
	"""
	qtys = {}
	if frappe.db.has_column("Tender Unit Type", "qty"):
		qtys = dict(frappe.db.sql("select name, qty from `tabTender Unit Type`"))

	for tender in frappe.get_all("Tender Unit Type", filters={"parenttype": "Tender"}, pluck="parent", distinct=True):
		doc = frappe.get_doc("Tender", tender)
		rows, units = [], {}
		for r in doc.unit_types:
			project_type = r.project_type or frappe.db.get_value("Tender Manifest", r.manifest, "project_type") or KITCHEN_PROJECT_TYPE
			for _i in range(max(1, cint(qtys.get(r.name)))):
				key = ((r.number or "").upper(), project_type)
				units[key] = units.get(key, 0) + 1
				rows.append({
					"unit_type": r.unit_type, "floor": r.floor, "number": r.number, "unit_name": r.unit_name,
					"manifest": r.manifest, "project_type": project_type, "unit_no": units[key],
				})
		frappe.db.delete("Tender Unit Type", {"parenttype": "Tender", "parent": doc.name})
		doc.set("unit_types", rows)
		for row in doc.unit_types:
			row.db_insert()
		link_unit_projects(doc)
