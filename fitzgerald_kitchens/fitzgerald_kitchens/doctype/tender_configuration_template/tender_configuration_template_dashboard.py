from frappe import _


def get_data():
	return {
		"fieldname": "template",
		"non_standard_fieldnames": {"Tender Configuration Template": "based_on"},
		"transactions": [
			{"label": _("Customer Templates"), "items": ["Tender Configuration Template"]},
			{"label": _("Used On"), "items": ["Tender", "Tender Manifest"]},
		],
	}
