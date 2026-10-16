import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	"""Tender's Tender From field was renamed Party Type; move its values (sites that had it)."""
	if frappe.db.has_column("Tender", "tender_from"):
		rename_field("Tender", "tender_from", "party_type")
