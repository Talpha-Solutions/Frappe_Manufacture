import frappe


def execute():
	"""Tender's Customer field became Tender From (Lead / Customer) + Party; carry existing values over.

	Runs after model sync: the old customer column is no longer in the doctype but is still in the
	table (Frappe doesn't drop columns), so it's read with SQL.
	"""
	if not frappe.db.has_column("Tender", "customer"):
		return

	for name, customer in frappe.db.sql(
		"""select name, customer from `tabTender`
		where ifnull(customer, '') != '' and ifnull(party_name, '') = ''"""
	):
		frappe.db.set_value(
			"Tender",
			name,
			{
				"tender_from": "Customer",
				"party_name": customer,
				"party_title": frappe.db.get_value("Customer", customer, "customer_name") or customer,
			},
			update_modified=False,
		)
