import frappe

RETIRED = {
	"Pre Production Manifest": (
		"section_break_units", "base_units", "wall_units", "tall_units", "drawer_packs",
		"section_break_cabinet_costing", "base_units_rate", "base_units_amount", "wall_units_rate", "wall_units_amount",
		"tall_units_rate", "tall_units_amount", "drawer_packs_rate", "drawer_packs_amount", "cabinets_total", "cabinet_prices_json",
	),
	"Tender Configuration Template": (
		"section_break_cabinet_mapping", "base_units_price_row", "wall_units_price_row", "tall_units_price_row",
		"drawer_packs_price_row", "cabinet_price_options_html",
	),
}


def execute():
	"""The per-kitchen cabinet counts (Base / Wall / Tall Units, Drawer Packs) priced from the template's
	Cabinet Unit Price Mapping were retired: cabinets are priced in the builder rows.

	The fields are gone from the doctypes; their columns stay in the tables (Frappe doesn't drop
	columns), so stored values aren't lost. Delete Property Setters left on those fields, e.g. a site
	that hid the Cabinets section in Customize Form.
	"""
	for doctype, fields in RETIRED.items():
		# the template may be renamed by now (Tender Configuration Template -> Pre Production Manifest Template)
		doctypes = [doctype, "Pre Production Manifest Template"] if doctype == "Tender Configuration Template" else [doctype]
		for name in frappe.get_all("Property Setter", filters={"doc_type": ["in", doctypes], "field_name": ["in", fields]}, pluck="name"):
			frappe.delete_doc("Property Setter", name, ignore_permissions=True)
