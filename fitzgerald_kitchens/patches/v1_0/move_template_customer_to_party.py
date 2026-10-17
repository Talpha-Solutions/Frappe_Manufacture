import frappe

from fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_configuration_template.tender_configuration_template import (
	party_title,
)


def execute():
	"""Tender Configuration Template's Customer became Party Type (Lead / Customer) + Party.

	Runs after model sync: the old customer column is no longer in the doctype but is still in the
	table (Frappe doesn't drop columns), so it's read with SQL.
	"""
	if not frappe.db.has_column("Tender Configuration Template", "customer"):
		return

	for name, customer in frappe.db.sql(
		"""select name, customer from `tabTender Configuration Template`
		where ifnull(customer, '') != '' and ifnull(party_name, '') = ''"""
	):
		frappe.db.set_value(
			"Tender Configuration Template",
			name,
			{"party_type": "Customer", "party_name": customer, "party_title": party_title("Customer", customer)},
			update_modified=False,
		)
