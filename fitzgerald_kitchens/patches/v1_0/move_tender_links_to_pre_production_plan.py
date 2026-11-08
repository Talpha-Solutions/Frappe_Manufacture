import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.model.utils.rename_field import rename_field

PPP = "Pre Production Plan"


def execute():
	"""After the Tender -> Pre Production Plan rename, move the fields that link to it onto their new
	names: Tender Manifest's tender -> pre_production_plan, and Project's custom fk_tender ->
	fk_pre_production_plan.

	Runs after model sync, so Tender Manifest's new column exists; the old columns are still in the
	tables (Frappe doesn't drop columns) and are copied. Fixtures are synced after patches, so the new
	Project custom field is made here, as the fixture has it, before its values are copied.
	"""
	if frappe.db.has_column("Tender Manifest", "tender") and frappe.db.has_column("Tender Manifest", "pre_production_plan"):
		rename_field("Tender Manifest", "tender", "pre_production_plan")

	if frappe.db.exists("Custom Field", "Project-fk_tender"):
		create_custom_field(
			"Project",
			{
				"fieldname": "fk_pre_production_plan",
				"label": PPP,
				"fieldtype": "Link",
				"options": PPP,
				"insert_after": "fk_tender_price_per_kitchen",
				"depends_on": "eval:doc.project_type == 'Site'",
				"description": "The pre production plan this site was created from",
				"read_only": 1,
			},
		)
		if frappe.db.has_column("Project", "fk_tender"):
			frappe.db.sql(
				"""update `tabProject` set fk_pre_production_plan = fk_tender
				where ifnull(fk_tender, '') != '' and ifnull(fk_pre_production_plan, '') = ''"""
			)
		frappe.delete_doc("Custom Field", "Project-fk_tender", ignore_permissions=True)

	# the default print format's Property Setter now comes from the fixture under the new doctype's name
	frappe.delete_doc_if_exists("Property Setter", "Tender-main-default_print_format")
	# a naming series set in Document Naming Settings (TDR-) would override the doctype's new PPP- series;
	# label customisations (Party -> Developer and the like) moved across with the rename and are kept
	for name in ("Tender-naming_series-options", "Tender-naming_series-default"):
		frappe.delete_doc_if_exists("Property Setter", name)
