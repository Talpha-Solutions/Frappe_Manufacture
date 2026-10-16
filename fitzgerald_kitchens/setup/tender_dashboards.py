# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from frappe import _


def add_tenders(data):
	"""Lead and Customer connections: their tenders and the tender templates made for them (both
	link through Party Type + Party)."""
	fieldnames = data.setdefault("non_standard_fieldnames", {})
	fieldnames["Tender"] = fieldnames["Tender Configuration Template"] = "party_name"
	data.setdefault("transactions", []).append(
		{"label": _("Tendering"), "items": ["Tender", "Tender Configuration Template"]}
	)
	return data
