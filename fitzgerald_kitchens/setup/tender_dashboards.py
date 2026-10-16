# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from frappe import _


def add_tenders(data):
	"""Lead and Customer connections: the tenders they're the party on (Tender From + Party)."""
	data.setdefault("non_standard_fieldnames", {})["Tender"] = "party_name"
	data.setdefault("transactions", []).append({"label": _("Tendering"), "items": ["Tender"]})
	return data
