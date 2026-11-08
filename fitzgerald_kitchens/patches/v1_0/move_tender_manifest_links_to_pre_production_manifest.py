import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.model.utils.rename_field import rename_field

PPM = "Pre Production Manifest"


def execute():
	"""After the Tender Manifest -> Pre Production Manifest rename, move the fields that link to it
	onto their new names: Project Unit Configuration's tender_manifest -> pre_production_manifest, and
	Project's custom fk_tender_manifest -> fk_pre_production_manifest.

	Runs after model sync, so the configuration's new column exists; the old columns are still in the
	tables and are copied. Fixtures are synced after patches, so the new Project custom field is made
	here, as the fixture has it. Unit Tender Price (fk_tender_manifest_price) fetches through that
	field, so it's pointed at the new one before the old one goes.
	"""
	if frappe.db.has_column("Project Unit Configuration", "tender_manifest") and frappe.db.has_column(
		"Project Unit Configuration", "pre_production_manifest"
	):
		rename_field("Project Unit Configuration", "tender_manifest", "pre_production_manifest")

	if frappe.db.exists("Custom Field", "Project-fk_tender_manifest"):
		create_custom_field(
			"Project",
			{
				"fieldname": "fk_pre_production_manifest",
				"label": "Unit Pre Production Manifest",
				"fieldtype": "Link",
				"options": PPM,
				"insert_after": "fk_site_tender_price_per_kitchen",
				"depends_on": "eval:doc.project_type != 'Site'",
				"description": "The pre production manifest this unit's room was priced with",
				"read_only": 1,
			},
		)
		if frappe.db.has_column("Project", "fk_tender_manifest"):
			frappe.db.sql(
				"""update `tabProject` set fk_pre_production_manifest = fk_tender_manifest
				where ifnull(fk_tender_manifest, '') != '' and ifnull(fk_pre_production_manifest, '') = ''"""
			)
		if frappe.db.exists("Custom Field", "Project-fk_tender_manifest_price"):
			frappe.db.set_value(
				"Custom Field",
				"Project-fk_tender_manifest_price",
				{"fetch_from": "fk_pre_production_manifest.tender_price_per_kitchen", "insert_after": "fk_pre_production_manifest"},
			)
		frappe.delete_doc("Custom Field", "Project-fk_tender_manifest", ignore_permissions=True)
		frappe.clear_cache(doctype="Project")

	# the default print format's Property Setter now comes from the fixture under the new doctype's name
	frappe.delete_doc_if_exists("Property Setter", "Tender Manifest-main-default_print_format")
