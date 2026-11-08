import json

import frappe

ROW = "Pre Production Manifest Template Row"
# spec details builder rows used to carry; costing replaced them (a BOM, a price list or the last
# purchase rate)
SPEC_ROW_KEYS = (
	"item_spec", "spec_list", "spec_reference", "specification", "spec_custom", "custom_spec", "exclude_from_price",
)


def execute():
	"""Specs are retired from tendering: manufactured items are costed from a BOM and bought-in items
	from a price list or their last purchase rate, so there is nothing left for a spec to do.

	- Spec-only template rows ("Exclude from Tender Price") are deleted, and the same rows are taken
	  out of the manifests using those templates, so manifests still match their template. They were
	  never counted in a price, so no total changes. The SPEC tag becomes MATERIAL.
	- The spec details are stripped from every manifest row.
	- The Item form's Item Specs table (two Custom Fields), Property Setters on the removed fields,
	  and the Item Spec and Spec List doctypes (with their records) are deleted.
	"""
	removed = set()  # (template, section, label)
	if frappe.db.has_column(ROW, "exclude_from_price"):
		for row in frappe.get_all(ROW, filters={"exclude_from_price": 1}, fields=["name", "parent", "section", "label"]):
			removed.add((row.parent, row.section, row.label))
			frappe.db.delete(ROW, {"name": row.name})
		for template in {template for template, _, _ in removed}:
			names = frappe.get_all(ROW, filters={"parent": template}, order_by="idx asc", pluck="name")
			for idx, name in enumerate(names, start=1):
				frappe.db.set_value(ROW, name, "idx", idx, update_modified=False)
	frappe.db.set_value(ROW, {"tag": "SPEC"}, "tag", "MATERIAL", update_modified=False)

	for manifest in frappe.get_all("Pre Production Manifest", fields=["name", "template", "config_rows_json"]):
		try:
			rows = json.loads(manifest.config_rows_json or "[]")
		except ValueError:
			continue
		if not isinstance(rows, list):
			continue
		kept = []
		for row in rows:
			if (manifest.template, row.get("section"), row.get("label")) in removed:
				continue
			kept.append({key: value for key, value in row.items() if key not in SPEC_ROW_KEYS})
		if kept != rows:
			frappe.db.set_value(
				"Pre Production Manifest", manifest.name, "config_rows_json", json.dumps(kept), update_modified=False
			)

	for name in ("Item-custom_item_specs_section", "Item-custom_item_specs_html"):
		frappe.delete_doc("Custom Field", name, ignore_missing=True, force=True)
	frappe.db.delete("Property Setter", {"doc_type": ["in", ["Pre Production Plan", "Pre Production Manifest"]], "field_name": "spec_list"})
	frappe.db.delete("Property Setter", {"doc_type": ROW, "field_name": "exclude_from_price"})
	frappe.db.delete("Property Setter", {"doc_type": ["in", ["Item Spec", "Spec List"]]})

	# Item Spec links to Spec List, so it goes first
	for doctype in ("Item Spec", "Spec List"):
		if frappe.db.exists("DocType", doctype):
			frappe.db.delete(doctype)
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
