# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# manifest field -> tender total it adds up into
TOTAL_FIELDS = {
	"kitchens_to_tender": "total_units",
	"cost_base": "total_cost_base",
	"margin_amount": "total_margin",
	"tender_price_total": "total_tender_price",
}


class Tender(Document):
	def validate(self):
		# the totals belong to the manifests; recompute rather than trust what the form sent
		self.update(_calculate_totals(self.name) if not self.is_new() else _empty_totals())


def update_tender_totals(tender: str | None):
	"""Re-add the linked manifests into a tender's totals (called when a manifest changes)."""
	if not tender or not frappe.db.exists("Tender", tender):
		return
	frappe.db.set_value("Tender", tender, _calculate_totals(tender), update_modified=False)


def _calculate_totals(tender: str) -> dict:
	manifests = frappe.get_all("Tender Manifest", filters={"tender": tender}, fields=list(TOTAL_FIELDS))
	totals = {total: sum(flt(m.get(field)) for m in manifests) for field, total in TOTAL_FIELDS.items()}
	totals["manifest_count"] = len(manifests)
	return totals


def _empty_totals() -> dict:
	return {"manifest_count": 0, **{total: 0 for total in TOTAL_FIELDS.values()}}


@frappe.whitelist()
def set_tender_status(tender: str, status: str):
	"""Change a tender's status (the field is read-only on the form; this is the Set Tender Status action)."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("write")
	options = (doc.meta.get_field("status").options or "").split("\n")
	if status not in options:
		frappe.throw(_("Status must be one of {0}").format(", ".join(options)))
	if doc.status == status:
		return
	doc.status = status
	doc.save()


@frappe.whitelist()
def get_tender_manifests(tender: str) -> dict:
	"""Rows for the manifest summary table on the Tender form, and the tender's totals.

	The totals are recalculated here too and corrected if the stored ones are out of date (e.g. a
	manifest changed without a save), so the form always shows the same figures as the table.
	"""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("read")
	if not frappe.has_permission("Tender Manifest", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	totals = _calculate_totals(tender)
	if any(flt(doc.get(field), 2) != flt(value, 2) for field, value in totals.items()):
		frappe.db.set_value("Tender", tender, totals, update_modified=False)

	manifests = frappe.get_all(
		"Tender Manifest",
		filters={"tender": tender},
		fields=[
			"name",
			"tender_name",
			"template",
			"kitchens_to_tender",
			"total_cost_per_kitchen",
			"tender_price_total",
		],
		order_by="creation asc",
	)
	return {"manifests": manifests, "totals": totals}
