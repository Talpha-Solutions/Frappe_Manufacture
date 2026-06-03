import frappe


def execute():
	"""Script reports must use the app module so Python resolves to fitzgerald_kitchens."""
	if not frappe.db.exists("Report", "Capacity Pipeline Report"):
		return
	frappe.db.set_value(
		"Report",
		"Capacity Pipeline Report",
		"module",
		"fitzgerald_kitchens",
		update_modified=False,
	)
