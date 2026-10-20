# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from fitzgerald_kitchens.setup.project_unit_fields import KITCHEN_PROJECT_TYPE
from fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_configuration_template.tender_configuration_template import (
	party_title,
	validate_party_type,
	validate_template_party,
)

# tasks for the unit projects a won tender creates, unless another template is picked
DEFAULT_PROJECT_TEMPLATE = "Main Development Template"

# manifest field -> tender total it adds up into
TOTAL_FIELDS = {
	"kitchens_to_tender": "total_units",
	"cost_base": "total_cost_base",
	"margin_amount": "total_margin",
	"tender_price_total": "total_tender_price",
}


class Tender(Document):
	def validate(self):
		validate_party_type(self.party_type)
		self.party_title = party_title(self.party_type, self.party_name)
		validate_template_party(self.template, self.party_type, self.party_name)
		self._set_unit_defaults()
		self._validate_unit_types()
		# the totals belong to the manifests; recompute rather than trust what the form sent
		self.update(_calculate_totals(self.name) if not self.is_new() else _empty_totals())

	def _set_unit_defaults(self):
		"""A won tender's Units tab starts with the site name, company and task template filled in
		(the workflow saves the tender when it's marked Won)."""
		if self.status != "Won":
			return
		self.unit_site_name = self.unit_site_name or self.tender_name
		self.company = self.company or frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		if not self.project_template and frappe.db.exists("Project Template", DEFAULT_PROJECT_TEMPLATE):
			self.project_template = DEFAULT_PROJECT_TEMPLATE

	def _validate_unit_types(self):
		"""Units tab: a row per unit (per apartment, per manifest, per one of its Qty). Rows sharing an Apt
		No are one apartment, which needs a Kitchen; its other units (Robe, Utility...) are created under
		it. An apartment's rows of a project type share one manifest and are numbered 1, 2..."""
		apartments: dict[str, dict] = {}
		for row in self.get("unit_types") or []:
			for field in ("unit_type", "floor", "number", "unit_name"):
				row.set(field, (row.get(field) or "").strip())
			label = frappe.bold(row.number)
			project_type = frappe.db.get_value("Tender Manifest", row.manifest, "project_type") if row.manifest else None
			row.project_type = project_type
			if row.manifest and frappe.db.get_value("Tender Manifest", row.manifest, "tender") != self.name:
				frappe.throw(_("Apt {0}: manifest {1} isn't one of this tender's manifests.").format(label, frappe.bold(row.manifest)))
			apt = apartments.setdefault(row.number.upper(), {"row": row, "project_types": {}})
			first = apt["row"]
			for field, name in (("unit_type", _("Apt Type")), ("floor", _("Floor")), ("unit_name", _("Unit Name"))):
				if row.get(field) != first.get(field):
					frappe.throw(_("Apt {0} has different {1} values on its rows.").format(label, name))
			same_type = apt["project_types"].setdefault(project_type, {"manifest": row.manifest, "units": 0})
			if same_type["manifest"] != row.manifest:
				frappe.throw(_("Apt {0} has two different {1} manifests; an apartment uses one per project type.").format(
					label, frappe.bold(project_type)))
			same_type["units"] += 1
			row.unit_no = same_type["units"]

		for apt in apartments.values():
			if KITCHEN_PROJECT_TYPE not in apt["project_types"]:
				frappe.throw(
					_("Apt {0} needs a Kitchen manifest; its other manifests are created under the kitchen.").format(
						frappe.bold(apt["row"].number)
					)
				)


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
			"project_type",
			"template",
			"kitchens_to_tender",
			"total_cost_per_kitchen",
			"tender_price_total",
		],
		order_by="creation asc",
	)
	return {"manifests": manifests, "totals": totals}
