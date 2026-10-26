# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""What the Tender Document print format shows: the client's copy of the tender, like the simplified
Excel (every line at tender price, no cost or margin), as a document that can be sent as a PDF.
"""

import re

import frappe
from frappe.contacts.doctype.address.address import get_company_address
from frappe.utils import cint, flt, money_in_words

from fitzgerald_kitchens.fitzgerald_kitchens.utils.tender_manifest_excel import (
	_group_rows,
	_line_values,
	_refs,
	_unit,
)
from fitzgerald_kitchens.setup.project_unit_fields import KITCHEN_PROJECT_TYPE


def get_tender_document(tender: str) -> dict:
	"""For the print format (a Jinja method): the tender's summary and one priced bill per manifest."""
	doc = frappe.get_doc("Tender", tender)
	doc.check_permission("print")
	company = doc.company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	currency = (company and frappe.get_cached_value("Company", company, "default_currency")) or "EUR"

	manifests = [
		frappe.get_doc("Tender Manifest", name)
		for name in frappe.get_all("Tender Manifest", filters={"tender": doc.name}, pluck="name", order_by="creation asc")
	]
	bills = [_bill(number, m) for number, m in enumerate(manifests, start=1)]
	total = sum(b["total"] for b in bills)
	return {
		"company": company,
		"company_details": _company_details(company),
		"currency": currency,
		"site_address": [line.strip() for line in (doc.site_address or "").splitlines() if line.strip()],
		"bills": bills,
		"units": sum(b["units"] for b in bills),
		"total": total,
		"total_in_words": money_in_words(total, currency) if total else "",
	}


def _company_details(company: str | None) -> dict:
	"""For the footer: the company's address on one line, and whichever contact details it has."""
	if not company:
		return {"address": "", "contacts": []}
	address = get_company_address(company).get("company_address_display") or ""
	lines = [line.strip(" ,") for line in re.split(r"<br\s*/?>|\n", address) if line.strip(" ,")]
	values = frappe.get_cached_value("Company", company, ["phone_no", "email", "website", "tax_id"], as_dict=True) or {}
	contacts = [
		values.get("phone_no"),
		values.get("email"),
		(values.get("website") or "").replace("https://", "").replace("http://", "").rstrip("/") or None,
		f"VAT No. {values['tax_id']}" if values.get("tax_id") else None,
	]
	return {"address": ", ".join(lines), "contacts": [c for c in contacts if c]}


def _bill(number: int, manifest) -> dict:
	"""One manifest's bill at tender price: its sections and lines, as the simplified Excel has them."""
	units = flt(manifest.kitchens_to_tender)
	sections = []
	for section, rows in _group_rows(manifest, client=True):
		# A, B, C... start again in each section, as on the Excel bill
		refs = _refs()
		lines = []
		for line in rows:
			description = _line_values(line, units, client=True)
			# a line nobody filled in (no item, no price) is left out of the client's copy
			if not (line.get("item_code") or line.get("is_charge")) and not line["per_unit"]:
				continue
			lines.append({
				"ref": next(refs),
				"description": description,
				"qty": flt(line.get("qty")),
				"unit": _unit(line),
				"rate": flt(line.get("rate")),
				"per_unit": line["per_unit"],
				"total": line["total"],
			})
		if not lines:
			continue
		sections.append({
			"number": len(sections) + 1,
			"title": section.title(),
			"lines": lines,
			"per_unit": sum(line["per_unit"] for line in lines),
			"total": sum(line["total"] for line in lines),
		})
	return {
		"number": number,
		"name": manifest.name,
		"title": manifest.tender_name or manifest.name,
		"project_type": manifest.project_type or KITCHEN_PROJECT_TYPE,
		"units": cint(units),
		"sections": sections,
		"per_unit": flt(manifest.tender_price_per_kitchen),
		"total": flt(manifest.tender_price_total),
	}
